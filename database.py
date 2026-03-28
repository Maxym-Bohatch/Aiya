from pathlib import Path

import psycopg2
from psycopg2.extras import Json

from config import settings


def get_connection():
    return psycopg2.connect(settings.database_url)


def ensure_schema():
    init_sql = Path(__file__).with_name("init.sql").read_text(encoding="utf-8")
    host_prompt_sql_path = Path(__file__).with_name("host_prompt.sql")
    host_prompt_sql = host_prompt_sql_path.read_text(encoding="utf-8") if host_prompt_sql_path.exists() else ""
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(init_sql)
        if host_prompt_sql.strip():
            cur.execute(host_prompt_sql)
        conn.commit()
    finally:
        if conn:
            conn.close()


def get_internal_user(platform, external_id, username_hint="User"):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_internal_id
            FROM aiya_social_links
            WHERE platform_name = %s AND external_id = %s
            """,
            (platform, external_id),
        )
        row = cur.fetchone()

        if row:
            ensure_user_settings(row[0], conn=conn)
            conn.commit()
            return row[0]

        cur.execute(
            "INSERT INTO aiya_users (username) VALUES (%s) RETURNING id",
            (username_hint,),
        )
        new_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO aiya_social_links (platform_name, external_id, user_internal_id)
            VALUES (%s, %s, %s)
            """,
            (platform, external_id, new_id),
        )
        ensure_user_settings(new_id, conn=conn)
        conn.commit()
        return new_id
    except Exception as e:
        print(f"Identity Error: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()


def ensure_user_settings(user_id, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_user_settings (
                user_id, tts_enabled, ocr_enabled, emoji_enabled,
                desktop_subtitles_enabled, image_generation_enabled
            )
            VALUES (%s, false, false, true, true, false)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id,),
        )
        if owns_conn:
            conn.commit()
    finally:
        if owns_conn and conn:
            conn.close()


def get_token_level(user_id, token):
    if not token:
        return 1

    admin_tokens = {settings.admin_token, *settings.extra_admin_tokens}
    admin_tokens.discard("")

    if token in admin_tokens:
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE aiya_users SET clearance_level = 10, token = %s WHERE id = %s",
                (token, user_id),
            )
            conn.commit()
            return 10
        except Exception:
            return 10
        finally:
            if conn:
                conn.close()

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT clearance_level FROM aiya_users WHERE token = %s", (token,))
        row = cur.fetchone()
        return row[0] if row else 1
    except Exception:
        return 1
    finally:
        if conn:
            conn.close()


def save_fact(user_id, fact_text, vector, level=1):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_facts (user_id, fact_text, embedding, required_level)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, fact_text)
            DO UPDATE SET
                embedding = EXCLUDED.embedding,
                required_level = EXCLUDED.required_level,
                last_used_at = CURRENT_TIMESTAMP
            """,
            (user_id, fact_text, vector, level),
        )
        conn.commit()
    except Exception as e:
        print(f"Fact error: {e}")
    finally:
        if conn:
            conn.close()


def find_smart_memories(owner_user_id, vector, limit=5, viewer_user_id=None, viewer_level=1):
    viewer_user_id = owner_user_id if viewer_user_id is None else viewer_user_id
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        if viewer_level >= 10:
            cur.execute(
                """
                SELECT id, fact_text
                FROM aiya_facts
                WHERE (user_id = %s OR user_id = 0)
                  AND recall_cooldown_until <= CURRENT_TIMESTAMP
                ORDER BY (embedding <=> %s::vector) ASC
                LIMIT %s
                """,
                (owner_user_id, vector, limit),
            )
        elif viewer_user_id == owner_user_id:
            cur.execute(
                """
                SELECT id, fact_text
                FROM aiya_facts
                WHERE (user_id = %s OR user_id = 0)
                  AND recall_cooldown_until <= CURRENT_TIMESTAMP
                ORDER BY (embedding <=> %s::vector) ASC
                LIMIT %s
                """,
                (owner_user_id, vector, limit),
            )
        else:
            cur.execute(
                """
                SELECT id, fact_text
                FROM aiya_facts
                WHERE (
                        user_id = 0
                        AND recall_cooldown_until <= CURRENT_TIMESTAMP
                      )
                   OR (
                        user_id = %s
                        AND recall_cooldown_until <= CURRENT_TIMESTAMP
                        AND EXISTS (
                            SELECT 1
                            FROM aiya_data_consents c
                            WHERE c.owner_user_id = %s
                              AND c.grantee_user_id = %s
                              AND c.can_access_private = true
                        )
                   )
                ORDER BY (embedding <=> %s::vector) ASC
                LIMIT %s
                """,
                (owner_user_id, owner_user_id, viewer_user_id, vector, limit),
            )

        rows = cur.fetchall()
        if rows:
            mark_facts_recalled([row[0] for row in rows])
        return [r[1] for r in rows]
    except Exception as e:
        print(f"RAG Error: {e}")
        return []
    finally:
        if conn:
            conn.close()


def mark_facts_recalled(fact_ids):
    if not fact_ids:
        return
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE aiya_facts
            SET
                use_count = use_count + 1,
                last_used_at = CURRENT_TIMESTAMP,
                recall_cooldown_until = CURRENT_TIMESTAMP + INTERVAL '10 minutes'
            WHERE id = ANY(%s)
            """,
            (fact_ids,),
        )
        conn.commit()
    finally:
        if conn:
            conn.close()


def save_chat_log(user_id, role, content):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO aiya_chat_history (user_id, role, content) VALUES (%s, %s, %s)",
            (user_id, role, content),
        )
        conn.commit()
    except Exception as e:
        print(f"Chat log error: {e}")
    finally:
        if conn:
            conn.close()


def get_recent_logs(user_id, limit=6):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT role, content
            FROM aiya_chat_history
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
        return "\n".join([f"{role}: {content}" for role, content in reversed(rows)])
    except Exception:
        return ""
    finally:
        if conn:
            conn.close()


def save_screen_observation(user_id, raw_text, summary="", source="desktop"):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_screen_observations (user_id, source, raw_text, summary)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, source, raw_text, summary),
        )
        conn.commit()
    finally:
        if conn:
            conn.close()


def get_recent_screen_context(user_id, limit=3):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COALESCE(summary, raw_text), created_at
            FROM aiya_screen_observations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
        return "\n".join(
            [f"[{created_at:%Y-%m-%d %H:%M}] {text}" for text, created_at in reversed(rows) if text]
        )
    finally:
        if conn:
            conn.close()


def update_user_state(user_id, mood, addon):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_state (user_id, mood, internal_goals)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                mood = EXCLUDED.mood,
                internal_goals = EXCLUDED.internal_goals,
                last_updated = CURRENT_TIMESTAMP
            """,
            (user_id, mood, addon),
        )
        conn.commit()
    except Exception as e:
        print(f"State update error: {e}")
    finally:
        if conn:
            conn.close()


def get_user_state(user_id):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT mood, internal_goals FROM aiya_state WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        return row if row else ("stable", "")
    except Exception:
        return ("stable", "")
    finally:
        if conn:
            conn.close()


def get_user_profile(user_id, first_name=""):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT profile_summary, clearance_level FROM aiya_users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return f"Користувач {first_name}", 1

        summary = row[0] if row[0] is not None else "Інформація відсутня."
        level = row[1] if row[1] is not None else 1
        return summary, level
    except Exception as e:
        print(f"Profile Fetch Error: {e}")
        return "Помилка завантаження профілю.", 1
    finally:
        if conn:
            conn.close()


def refresh_user_profile_summary(user_id, limit=8):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT fact_text
            FROM aiya_facts
            WHERE user_id = %s
            ORDER BY use_count DESC, created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        facts = [row[0] for row in cur.fetchall() if row and row[0]]
        if not facts:
            return
        summary = "; ".join(facts[:limit])[:900]
        cur.execute(
            "UPDATE aiya_users SET profile_summary = %s WHERE id = %s",
            (summary, user_id),
        )
        conn.commit()
    except Exception as e:
        print(f"Profile Summary Error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def get_prompt(slug):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT content FROM aiya_prompts WHERE slug = %s", (slug,))
        row = cur.fetchone()
        return row[0] if row else "Ти Айя, іронічна цифрова особистість."
    except Exception:
        return "Ти Айя, іронічна цифрова особистість."
    finally:
        if conn:
            conn.close()


def update_graph(user_id, to_add, to_remove):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        for triple in to_add:
            if len(triple) == 3:
                subject = resolve_alias(user_id, triple[0])
                relation = triple[1]
                obj = resolve_alias(user_id, triple[2])
                cur.execute(
                    """
                    INSERT INTO aiya_graph (user_id, subject, relation, object)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (user_id, subject, relation, obj),
                )

        for rel in to_remove:
            if len(rel) >= 2:
                subject = resolve_alias(user_id, rel[0])
                cur.execute(
                    """
                    DELETE FROM aiya_graph
                    WHERE user_id = %s AND subject = %s AND relation = %s
                    """,
                    (user_id, subject, rel[1]),
                )
        conn.commit()
    except Exception as e:
        print(f"Graph Update Error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def find_graph_context(user_id, query_text, limit=5):
    normalized = (query_text or "").strip().lower()
    if not normalized:
        return []
    tokens = [part for part in normalized.replace(",", " ").replace(".", " ").split() if len(part) >= 3][:6]
    if not tokens:
        tokens = [normalized[:32]]

    clauses = []
    params = [user_id]
    for token in tokens:
        pattern = f"%{token}%"
        clauses.append("(LOWER(subject) LIKE %s OR LOWER(relation) LIKE %s OR LOWER(object) LIKE %s)")
        params.extend([pattern, pattern, pattern])
    params.append(limit)

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT subject, relation, object
            FROM aiya_graph
            WHERE user_id = %s
              AND ({' OR '.join(clauses)})
            ORDER BY created_at DESC
            LIMIT %s
            """,
            params,
        )
        return [f"{subject} -> {relation} -> {obj}" for subject, relation, obj in cur.fetchall()]
    except Exception as e:
        print(f"Graph Context Error: {e}")
        return []
    finally:
        if conn:
            conn.close()


def save_wiki_entries(query, language, items):
    if not items:
        return
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        for item in items:
            cur.execute(
                """
                INSERT INTO aiya_wiki_cache (query, language, title, description, extract, url)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    query,
                    language,
                    item.get("title", ""),
                    item.get("description", ""),
                    item.get("extract", ""),
                    item.get("url", ""),
                ),
            )
        conn.commit()
    except Exception as e:
        print(f"Wiki Cache Save Error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def find_wiki_context(query_text, language="uk", limit=3):
    normalized = (query_text or "").strip().lower()
    if not normalized:
        return []
    tokens = [part for part in normalized.replace(",", " ").replace(".", " ").split() if len(part) >= 4][:6]
    if not tokens:
        tokens = [normalized[:32]]

    clauses = []
    params = [language]
    for token in tokens:
        pattern = f"%{token}%"
        clauses.append("(LOWER(query) LIKE %s OR LOWER(title) LIKE %s OR LOWER(extract) LIKE %s)")
        params.extend([pattern, pattern, pattern])
    params.append(limit)

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT title, description, extract, url
            FROM aiya_wiki_cache
            WHERE language = %s
              AND ({' OR '.join(clauses)})
            ORDER BY created_at DESC
            LIMIT %s
            """,
            params,
        )
        rows = cur.fetchall()
        result = []
        for title, description, extract, url in rows:
            line = f"{title}: {(extract or description or '').strip()}"
            if url:
                line += f" [{url}]"
            result.append(line)
        return result
    except Exception as e:
        print(f"Wiki Context Error: {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_user_settings(user_id):
    ensure_user_settings(user_id)
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                tts_enabled,
                ocr_enabled,
                emoji_enabled,
                desktop_subtitles_enabled,
                image_generation_enabled
            FROM aiya_user_settings
            WHERE user_id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return {
                "tts_enabled": False,
                "ocr_enabled": False,
                "emoji_enabled": True,
                "desktop_subtitles_enabled": True,
                "image_generation_enabled": False,
            }
        return {
            "tts_enabled": row[0],
            "ocr_enabled": row[1],
            "emoji_enabled": row[2],
            "desktop_subtitles_enabled": row[3],
            "image_generation_enabled": row[4],
        }
    finally:
        if conn:
            conn.close()


def update_user_settings(user_id, updates):
    allowed_fields = {
        "tts_enabled",
        "ocr_enabled",
        "emoji_enabled",
        "desktop_subtitles_enabled",
        "image_generation_enabled",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return get_user_settings(user_id)

    ensure_user_settings(user_id)
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        set_clause = ", ".join([f"{field} = %s" for field in filtered])
        params = list(filtered.values()) + [user_id]
        cur.execute(
            f"UPDATE aiya_user_settings SET {set_clause} WHERE user_id = %s",
            params,
        )
        conn.commit()
        return get_user_settings(user_id)
    finally:
        if conn:
            conn.close()


def upsert_consent(owner_user_id, grantee_user_id, can_access_private):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_data_consents (owner_user_id, grantee_user_id, can_access_private)
            VALUES (%s, %s, %s)
            ON CONFLICT (owner_user_id, grantee_user_id) DO UPDATE SET
                can_access_private = EXCLUDED.can_access_private,
                updated_at = CURRENT_TIMESTAMP
            """,
            (owner_user_id, grantee_user_id, can_access_private),
        )
        conn.commit()
    finally:
        if conn:
            conn.close()


def has_consent(owner_user_id, grantee_user_id):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT can_access_private
            FROM aiya_data_consents
            WHERE owner_user_id = %s AND grantee_user_id = %s
            """,
            (owner_user_id, grantee_user_id),
        )
        row = cur.fetchone()
        return bool(row and row[0])
    finally:
        if conn:
            conn.close()


def upsert_alias(user_id, alias, canonical_name):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_aliases (user_id, alias, canonical_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, alias) DO UPDATE SET canonical_name = EXCLUDED.canonical_name
            """,
            (user_id, alias.lower(), canonical_name),
        )
        conn.commit()
    finally:
        if conn:
            conn.close()


def resolve_alias(user_id, name):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT canonical_name
            FROM aiya_aliases
            WHERE user_id = %s AND alias = %s
            """,
            (user_id, name.lower()),
        )
        row = cur.fetchone()
        return row[0] if row else name
    finally:
        if conn:
            conn.close()


def log_game_event(session_id, event_type, screen_summary="", action_name="", action_payload=None, outcome=""):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_game_events (session_id, event_type, screen_summary, action_name, action_payload, outcome)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (session_id, event_type, screen_summary, action_name, Json(action_payload or {}), outcome),
        )
        cur.execute(
            "UPDATE aiya_game_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (session_id,),
        )
        conn.commit()
    finally:
        if conn:
            conn.close()


def get_recent_game_events(session_id, limit=8):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT event_type, screen_summary, action_name, outcome
            FROM aiya_game_events
            WHERE session_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (session_id, limit),
        )
        rows = cur.fetchall()
        return list(reversed(rows))
    finally:
        if conn:
            conn.close()


DEFAULT_GAME_PROFILE = {
    "profile_name": "default",
    "autoplay": False,
    "simulate_only": False,
    "require_confirmation": False,
    "learning_enabled": True,
    "max_actions_per_step": 2,
    "action_cooldown_ms": 900,
    "planner_interval_ms": 2200,
    "preferred_input_mode": "hybrid",
    "target_objective": "",
    "notes": "",
    "profile_settings": {},
}


def get_game_profile(user_id, game_name, profile_name="default"):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT profile_name, autoplay, simulate_only, require_confirmation, learning_enabled,
                   max_actions_per_step, action_cooldown_ms, planner_interval_ms,
                   preferred_input_mode, target_objective, notes, profile_settings
            FROM aiya_game_profiles
            WHERE user_id = %s AND game_name = %s AND profile_name = %s
            """,
            (user_id, game_name, profile_name),
        )
        row = cur.fetchone()
        if not row:
            profile = dict(DEFAULT_GAME_PROFILE)
            profile["profile_name"] = profile_name or "default"
            return profile
        return {
            "profile_name": row[0],
            "autoplay": bool(row[1]),
            "simulate_only": bool(row[2]),
            "require_confirmation": bool(row[3]),
            "learning_enabled": bool(row[4]),
            "max_actions_per_step": int(row[5] or 2),
            "action_cooldown_ms": int(row[6] or 900),
            "planner_interval_ms": int(row[7] or 2200),
            "preferred_input_mode": row[8] or "hybrid",
            "target_objective": row[9] or "",
            "notes": row[10] or "",
            "profile_settings": row[11] or {},
        }
    finally:
        if conn:
            conn.close()


def upsert_game_profile(user_id, game_name, profile_name="default", settings_map=None):
    settings_map = settings_map or {}
    profile = dict(DEFAULT_GAME_PROFILE)
    profile["profile_name"] = profile_name or "default"
    profile.update({key: value for key, value in settings_map.items() if key in profile})
    extra_settings = settings_map.get("profile_settings")
    if extra_settings is None:
        known_keys = set(profile.keys())
        extra_settings = {key: value for key, value in settings_map.items() if key not in known_keys}
    profile["profile_settings"] = extra_settings or {}

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_game_profiles (
                user_id, game_name, profile_name, autoplay, simulate_only,
                require_confirmation, learning_enabled, max_actions_per_step,
                action_cooldown_ms, planner_interval_ms, preferred_input_mode,
                target_objective, notes, profile_settings
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, game_name, profile_name) DO UPDATE SET
                autoplay = EXCLUDED.autoplay,
                simulate_only = EXCLUDED.simulate_only,
                require_confirmation = EXCLUDED.require_confirmation,
                learning_enabled = EXCLUDED.learning_enabled,
                max_actions_per_step = EXCLUDED.max_actions_per_step,
                action_cooldown_ms = EXCLUDED.action_cooldown_ms,
                planner_interval_ms = EXCLUDED.planner_interval_ms,
                preferred_input_mode = EXCLUDED.preferred_input_mode,
                target_objective = EXCLUDED.target_objective,
                notes = EXCLUDED.notes,
                profile_settings = EXCLUDED.profile_settings,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                game_name,
                profile["profile_name"],
                profile["autoplay"],
                profile["simulate_only"],
                profile["require_confirmation"],
                profile["learning_enabled"],
                profile["max_actions_per_step"],
                profile["action_cooldown_ms"],
                profile["planner_interval_ms"],
                profile["preferred_input_mode"],
                profile["target_objective"],
                profile["notes"],
                Json(profile["profile_settings"]),
            ),
        )
        conn.commit()
    finally:
        if conn:
            conn.close()
    return get_game_profile(user_id, game_name, profile["profile_name"])


def create_or_get_game_session(user_id, game_name, goal="", profile_name="default", metadata=None):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id
            FROM aiya_game_sessions
            WHERE user_id = %s AND game_name = %s AND profile_name = %s AND status IN ('idle', 'running')
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id, game_name, profile_name),
        )
        row = cur.fetchone()
        if row:
            session_id = row[0]
            cur.execute(
                """
                UPDATE aiya_game_sessions
                SET goal = %s, session_metadata = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (goal, Json(metadata or {}), session_id),
            )
            conn.commit()
            return session_id

        cur.execute(
            """
            INSERT INTO aiya_game_sessions (user_id, game_name, profile_name, goal, status, session_metadata)
            VALUES (%s, %s, %s, %s, 'running', %s)
            RETURNING id
            """,
            (user_id, game_name, profile_name, goal, Json(metadata or {})),
        )
        session_id = cur.fetchone()[0]
        conn.commit()
        return session_id
    finally:
        if conn:
            conn.close()


def update_game_session_status(session_id, status, metadata=None):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        if metadata is None:
            cur.execute(
                "UPDATE aiya_game_sessions SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (status, session_id),
            )
        else:
            cur.execute(
                """
                UPDATE aiya_game_sessions
                SET status = %s, session_metadata = session_metadata || %s::jsonb, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (status, Json(metadata), session_id),
            )
        conn.commit()
    finally:
        if conn:
            conn.close()


def record_game_feedback(
    session_id,
    verdict,
    score=0,
    note="",
    screen_summary="",
    action_name="",
    action_payload=None,
):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_game_feedback (
                session_id, verdict, score, note, screen_summary, action_name, action_payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (session_id, verdict, score, note, screen_summary, action_name, Json(action_payload or {})),
        )
        feedback_id = cur.fetchone()[0]
        cur.execute(
            "UPDATE aiya_game_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (session_id,),
        )
        conn.commit()
        return feedback_id
    finally:
        if conn:
            conn.close()


def get_recent_game_feedback(session_id, limit=6):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT verdict, score, note, screen_summary, action_name, action_payload, created_at
            FROM aiya_game_feedback
            WHERE session_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (session_id, limit),
        )
        return list(reversed(cur.fetchall()))
    finally:
        if conn:
            conn.close()


def save_game_learning_note(user_id, game_name, profile_name, cue, lesson, confidence=0.5, feedback=""):
    cue = (cue or "").strip()[:240]
    lesson = (lesson or "").strip()[:500]
    if not cue or not lesson:
        return None
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_game_learning_notes (
                user_id, game_name, profile_name, cue, lesson, confidence, last_feedback
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, game_name, profile_name, cue, lesson) DO UPDATE SET
                confidence = LEAST(1.0, GREATEST(0.05, (aiya_game_learning_notes.confidence + EXCLUDED.confidence) / 2.0)),
                times_reinforced = aiya_game_learning_notes.times_reinforced + 1,
                last_feedback = EXCLUDED.last_feedback,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (user_id, game_name, profile_name, cue, lesson, confidence, feedback),
        )
        note_id = cur.fetchone()[0]
        conn.commit()
        return note_id
    finally:
        if conn:
            conn.close()


def get_game_learning_notes(user_id, game_name, profile_name="default", limit=6):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cue, lesson, confidence, times_reinforced, last_feedback, updated_at
            FROM aiya_game_learning_notes
            WHERE user_id = %s AND game_name = %s AND profile_name = %s
            ORDER BY confidence DESC, updated_at DESC
            LIMIT %s
            """,
            (user_id, game_name, profile_name, limit),
        )
        return cur.fetchall()
    finally:
        if conn:
            conn.close()


def get_game_session_snapshot(session_id):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, game_name, profile_name, goal, status, session_metadata, created_at, updated_at
            FROM aiya_game_sessions
            WHERE id = %s
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cur.execute(
            """
            SELECT verdict, score, note, action_name, created_at
            FROM aiya_game_feedback
            WHERE session_id = %s
            ORDER BY created_at DESC
            LIMIT 5
            """,
            (session_id,),
        )
        feedback = list(reversed(cur.fetchall()))
        cur.execute(
            """
            SELECT event_type, action_name, outcome, created_at
            FROM aiya_game_events
            WHERE session_id = %s
            ORDER BY created_at DESC
            LIMIT 8
            """,
            (session_id,),
        )
        events = list(reversed(cur.fetchall()))
        return {
            "session_id": row[0],
            "user_id": row[1],
            "game_name": row[2],
            "profile_name": row[3],
            "goal": row[4],
            "status": row[5],
            "metadata": row[6] or {},
            "created_at": row[7].isoformat() if row[7] else None,
            "updated_at": row[8].isoformat() if row[8] else None,
            "recent_feedback": [
                {
                    "verdict": item[0],
                    "score": item[1],
                    "note": item[2],
                    "action_name": item[3],
                    "created_at": item[4].isoformat() if item[4] else None,
                }
                for item in feedback
            ],
            "recent_events": [
                {
                    "event_type": item[0],
                    "action_name": item[1],
                    "outcome": item[2],
                    "created_at": item[3].isoformat() if item[3] else None,
                }
                for item in events
            ],
        }
    finally:
        if conn:
            conn.close()


def get_robot_state():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT profile_name, body_mode, notes, state_payload, updated_at
            FROM aiya_robot_state
            WHERE id = 1
            """
        )
        row = cur.fetchone()
        if not row:
            return {"profile_name": "default", "body_mode": "idle", "notes": "", "state_payload": {}, "updated_at": None}
        return {
            "profile_name": row[0],
            "body_mode": row[1],
            "notes": row[2],
            "state_payload": row[3] or {},
            "updated_at": row[4].isoformat() if row[4] else None,
        }
    finally:
        if conn:
            conn.close()


def update_robot_state(profile_name=None, body_mode=None, notes=None, state_payload=None):
    current = get_robot_state()
    payload = current.get("state_payload", {})
    if isinstance(state_payload, dict):
        payload = {**payload, **state_payload}
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_robot_state (id, profile_name, body_mode, notes, state_payload, updated_at)
            VALUES (1, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO UPDATE SET
                profile_name = EXCLUDED.profile_name,
                body_mode = EXCLUDED.body_mode,
                notes = EXCLUDED.notes,
                state_payload = EXCLUDED.state_payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                profile_name or current.get("profile_name", "default"),
                body_mode or current.get("body_mode", "idle"),
                notes if notes is not None else current.get("notes", ""),
                Json(payload),
            ),
        )
        conn.commit()
        return get_robot_state()
    finally:
        if conn:
            conn.close()


def save_robot_sensor_frame(source, sensor_type, payload):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_robot_sensor_frames (source, sensor_type, payload)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (source, sensor_type, Json(payload or {})),
        )
        row = cur.fetchone()
        conn.commit()
        return {"id": row[0], "created_at": row[1].isoformat() if row[1] else None}
    finally:
        if conn:
            conn.close()


def get_recent_robot_sensor_frames(limit=20):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, source, sensor_type, payload, created_at
            FROM aiya_robot_sensor_frames
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "source": row[1],
                "sensor_type": row[2],
                "payload": row[3] or {},
                "created_at": row[4].isoformat() if row[4] else None,
            }
            for row in rows
        ]
    finally:
        if conn:
            conn.close()


def queue_robot_command(target, command_type, payload):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO aiya_robot_command_queue (target, command_type, payload)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (target, command_type, Json(payload or {})),
        )
        row = cur.fetchone()
        conn.commit()
        return {"command_id": row[0], "created_at": row[1].isoformat() if row[1] else None}
    finally:
        if conn:
            conn.close()


def claim_next_robot_command(target):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, target, command_type, payload, created_at
            FROM aiya_robot_command_queue
            WHERE target = %s AND status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (target,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cur.execute(
            """
            UPDATE aiya_robot_command_queue
            SET status = 'claimed', claimed_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (row[0],),
        )
        conn.commit()
        return {
            "command_id": row[0],
            "target": row[1],
            "command_type": row[2],
            "payload": row[3] or {},
            "created_at": row[4].isoformat() if row[4] else None,
        }
    finally:
        if conn:
            conn.close()


def complete_robot_command(command_id, status="completed", result_payload=None):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE aiya_robot_command_queue
            SET status = %s,
                result_payload = %s,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (status, Json(result_payload or {}), command_id),
        )
        conn.commit()
        return {"ok": True, "command_id": command_id, "status": status}
    finally:
        if conn:
            conn.close()
