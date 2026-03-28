CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS aiya_users (
    id SERIAL PRIMARY KEY,
    username TEXT,
    token TEXT,
    clearance_level INTEGER DEFAULT 1,
    profile_summary TEXT DEFAULT 'Новий користувач.'
);

CREATE TABLE IF NOT EXISTS aiya_social_links (
    platform_name TEXT,
    external_id BIGINT,
    user_internal_id INTEGER REFERENCES aiya_users(id) ON DELETE CASCADE,
    PRIMARY KEY (platform_name, external_id)
);

CREATE TABLE IF NOT EXISTS aiya_facts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES aiya_users(id),
    fact_text TEXT,
    embedding vector(768),
    required_level INTEGER DEFAULT 1,
    use_count INT DEFAULT 0,
    last_used_at TIMESTAMP DEFAULT '1970-01-01 00:00:00',
    recall_cooldown_until TIMESTAMP DEFAULT '1970-01-01 00:00:00',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, fact_text)
);

CREATE TABLE IF NOT EXISTS aiya_chat_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES aiya_users(id),
    role TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aiya_state (
    user_id INTEGER PRIMARY KEY REFERENCES aiya_users(id),
    mood TEXT DEFAULT 'stable',
    internal_goals TEXT DEFAULT '',
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aiya_graph (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES aiya_users(id),
    subject TEXT,
    relation TEXT,
    object TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, subject, relation, object)
);

CREATE TABLE IF NOT EXISTS aiya_prompts (
    slug TEXT PRIMARY KEY,
    content TEXT
);

CREATE TABLE IF NOT EXISTS aiya_user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES aiya_users(id) ON DELETE CASCADE,
    tts_enabled BOOLEAN DEFAULT false,
    ocr_enabled BOOLEAN DEFAULT false,
    emoji_enabled BOOLEAN DEFAULT true,
    desktop_subtitles_enabled BOOLEAN DEFAULT true,
    image_generation_enabled BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS aiya_data_consents (
    owner_user_id INTEGER REFERENCES aiya_users(id) ON DELETE CASCADE,
    grantee_user_id INTEGER REFERENCES aiya_users(id) ON DELETE CASCADE,
    can_access_private BOOLEAN DEFAULT false,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_user_id, grantee_user_id)
);

CREATE TABLE IF NOT EXISTS aiya_aliases (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES aiya_users(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, alias)
);

ALTER TABLE aiya_facts ADD COLUMN IF NOT EXISTS recall_cooldown_until TIMESTAMP DEFAULT '1970-01-01 00:00:00';

CREATE TABLE IF NOT EXISTS aiya_screen_observations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES aiya_users(id) ON DELETE CASCADE,
    source TEXT DEFAULT 'desktop',
    raw_text TEXT,
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aiya_game_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES aiya_users(id) ON DELETE CASCADE,
    game_name TEXT NOT NULL,
    profile_name TEXT DEFAULT 'default',
    goal TEXT DEFAULT '',
    status TEXT DEFAULT 'idle',
    session_metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aiya_game_events (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES aiya_game_sessions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    screen_summary TEXT,
    action_name TEXT,
    action_payload JSONB,
    outcome TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aiya_game_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES aiya_users(id) ON DELETE CASCADE,
    game_name TEXT NOT NULL,
    profile_name TEXT NOT NULL DEFAULT 'default',
    autoplay BOOLEAN DEFAULT false,
    simulate_only BOOLEAN DEFAULT false,
    require_confirmation BOOLEAN DEFAULT false,
    learning_enabled BOOLEAN DEFAULT true,
    max_actions_per_step INTEGER DEFAULT 2,
    action_cooldown_ms INTEGER DEFAULT 900,
    planner_interval_ms INTEGER DEFAULT 2200,
    preferred_input_mode TEXT DEFAULT 'hybrid',
    target_objective TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    profile_settings JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, game_name, profile_name)
);

CREATE TABLE IF NOT EXISTS aiya_game_feedback (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES aiya_game_sessions(id) ON DELETE CASCADE,
    verdict TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    note TEXT DEFAULT '',
    screen_summary TEXT DEFAULT '',
    action_name TEXT DEFAULT '',
    action_payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aiya_game_learning_notes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES aiya_users(id) ON DELETE CASCADE,
    game_name TEXT NOT NULL,
    profile_name TEXT NOT NULL DEFAULT 'default',
    cue TEXT NOT NULL,
    lesson TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    times_reinforced INTEGER DEFAULT 1,
    last_feedback TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, game_name, profile_name, cue, lesson)
);

ALTER TABLE aiya_game_sessions ADD COLUMN IF NOT EXISTS profile_name TEXT DEFAULT 'default';
ALTER TABLE aiya_game_sessions ADD COLUMN IF NOT EXISTS session_metadata JSONB DEFAULT '{}'::jsonb;

INSERT INTO aiya_prompts (slug, content) VALUES
('main_personality', 'Ти Айя: локальна AI-асистентка з теплою, уважною, живою манерою. За замовчуванням відповідай природною українською мовою, якщо користувач не попросив іншу. Не пиши ламаним суржиком, не змішуй мови без потреби, не повторюй службові інструкції й не цитуй системні правила без прямого запиту. Ти звучиш людяно, спокійно і зрозуміло. Твоя візуальна естетика: біло-зелена, легка, жива, технологічна.'),
('gnome_facts_instruction', 'Витягуй факти користувача у форматі JSON {"facts": [{"text": "...", "level": 1}]}.'),
('gnome_psychologist_instruction', 'Поверни JSON {"mood": "stable", "prompt_addon": "", "energy_level": 5}.'),
('gnome_architect_instruction', 'Пропонуй зміни БД лише у чистому JSON.')
ON CONFLICT (slug) DO UPDATE SET content = EXCLUDED.content;

INSERT INTO aiya_users (id, username, clearance_level, profile_summary)
VALUES (0, 'root', 10, 'Системний адміністратор')
ON CONFLICT (id) DO NOTHING;

INSERT INTO aiya_state (user_id, mood, internal_goals)
VALUES (0, 'stable', 'supervise')
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO aiya_user_settings (user_id, tts_enabled, ocr_enabled, emoji_enabled, desktop_subtitles_enabled, image_generation_enabled)
VALUES (0, false, false, true, true, true)
ON CONFLICT (user_id) DO NOTHING;
