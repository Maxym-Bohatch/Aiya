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


def create_or_get_game_session(user_id, game_name, goal=""):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id
            FROM aiya_game_sessions
            WHERE user_id = %s AND game_name = %s AND status IN ('idle', 'running')
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_id, game_name),
        )
        row = cur.fetchone()
        if row:
            session_id = row[0]
            cur.execute(
                """
                UPDATE aiya_game_sessions
                SET goal = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (goal, session_id),
            )
            conn.commit()
            return session_id

        cur.execute(
            """
            INSERT INTO aiya_game_sessions (user_id, game_name, goal, status)
            VALUES (%s, %s, %s, 'running')
            RETURNING id
            """,
            (user_id, game_name, goal),
        )
        session_id = cur.fetchone()[0]
        conn.commit()
        return session_id
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
