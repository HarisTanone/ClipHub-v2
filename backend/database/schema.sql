-- ═══════════════════════════════════════════════════════════════════════════════
-- AutoCliper Backend v0.4 — SQLite Database Schema
-- File: data/autoclip.db
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─── Jobs Table ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE,
    youtube_url TEXT NOT NULL,
    video_duration REAL DEFAULT NULL,
    status TEXT NOT NULL DEFAULT 'validating',
    render_progress TEXT DEFAULT NULL,
    error_message TEXT DEFAULT NULL,
    error_details TEXT DEFAULT NULL,
    clips_data TEXT DEFAULT NULL,
    clips_total INTEGER NOT NULL DEFAULT 0,
    clips_success INTEGER NOT NULL DEFAULT 0,
    clips_failed INTEGER NOT NULL DEFAULT 0,
    style_preset TEXT NOT NULL DEFAULT 'bold_black',
    target_aspect_ratio TEXT NOT NULL DEFAULT '9:16',
    hook_engine TEXT NOT NULL DEFAULT 'v3',
    hook_style TEXT NOT NULL DEFAULT '',
    broll_enabled INTEGER NOT NULL DEFAULT 1,
    autogrid_enabled INTEGER NOT NULL DEFAULT 0,
    -- v3.0 Remotion Integration Fields
    use_remotion INTEGER NOT NULL DEFAULT 0,
    ai_layer_enabled INTEGER NOT NULL DEFAULT 0,
    threejs_enabled INTEGER NOT NULL DEFAULT 0,
    scene_graphs TEXT DEFAULT NULL,
    remotion_quality TEXT DEFAULT 'medium',
    user_id INTEGER DEFAULT NULL,
    video_id TEXT DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_job_id ON jobs(job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_video_id ON jobs(video_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);

-- ─── Transcript Cache Table ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS transcript_cache (
    video_id TEXT PRIMARY KEY,
    transcript_json TEXT NOT NULL,
    whisper_model_hash TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'auto',
    duration_seconds REAL NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ─── Roles Table ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    is_system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─── Permissions Table ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─── Role-Permission Mapping ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
);

-- ─── Users Table ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    role_id INTEGER DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT DEFAULT NULL,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role_id);

-- ─── Refresh Tokens Table ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at);

-- ─── Seed: Default Roles ─────────────────────────────────────────────────────

INSERT OR IGNORE INTO roles (id, name, description, is_system) VALUES
    (1, 'superadmin', 'Full system access', 1),
    (2, 'editor', 'Can create and manage jobs', 1),
    (3, 'viewer', 'Read-only access', 1);

-- ─── Seed: Default Permissions ───────────────────────────────────────────────

INSERT OR IGNORE INTO permissions (code, name, category) VALUES
    ('jobs:create', 'Create Jobs', 'jobs'),
    ('jobs:read', 'View Jobs', 'jobs'),
    ('jobs:delete', 'Delete Jobs', 'jobs'),
    ('styles:update', 'Update Styles', 'styles'),
    ('system:admin', 'System Administration', 'system');

-- ─── Seed: Role-Permission Mapping ──────────────────────────────────────────

INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
SELECT 1, id FROM permissions;

INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
SELECT 2, id FROM permissions WHERE code IN ('jobs:create', 'jobs:read', 'styles:update');

INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
SELECT 3, id FROM permissions WHERE code = 'jobs:read';

-- ─── B-Roll Templates (v0.4) ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS broll_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    component TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'motion_typography',
    description TEXT DEFAULT NULL,
    default_duration_ms INTEGER NOT NULL DEFAULT 2000,
    config TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_broll_templates_category ON broll_templates(category);

-- ─── Job Clip B-Rolls (v0.4) ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS job_clip_brolls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    clip_rank INTEGER NOT NULL,
    template_id TEXT NOT NULL,
    at_time REAL NOT NULL,
    keyword_text TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 2000,
    rendered_path TEXT DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (template_id) REFERENCES broll_templates(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_job_clip_brolls_job ON job_clip_brolls(job_id, clip_rank);

-- ─── Seed: Default B-Roll Templates ─────────────────────────────────────────

INSERT OR IGNORE INTO broll_templates (id, name, component, description, default_duration_ms) VALUES
    ('word_pop_typography', 'Word Pop', 'WordPopBroll', 'Kata kunci muncul dengan scale/pop di atas background gradient', 2000),
    ('line_reveal_typography', 'Line Reveal', 'LineRevealBroll', 'Baris teks reveal dengan mask wipe, gaya editorial', 2500),
    ('particle_text_burst', 'Particle Burst', 'ParticleBurstBroll', 'Teks terbentuk dari partikel/noise, energetic', 3000);

-- ═══════════════════════════════════════════════════════════════════════════════
-- v3.0 Remotion Integration Tables
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─── Style Presets Table ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS style_presets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT NULL,
    -- Colors
    primary_color TEXT NOT NULL DEFAULT '#ffffff',
    secondary_color TEXT NOT NULL DEFAULT '#ffcc00',
    background_accent TEXT NOT NULL DEFAULT '#000000',
    -- Typography
    typography_mood TEXT NOT NULL DEFAULT 'bold_impact',
    hook_animation TEXT NOT NULL DEFAULT 'fade_scale',
    -- Energy & Transitions
    energy_level TEXT NOT NULL DEFAULT 'medium',
    transition_style TEXT NOT NULL DEFAULT 'smooth',
    -- Subtitle
    subtitle_position TEXT NOT NULL DEFAULT 'bottom',
    subtitle_uppercase INTEGER NOT NULL DEFAULT 0,
    -- Feature Flags
    enable_threejs INTEGER NOT NULL DEFAULT 0,
    enable_ai_layer INTEGER NOT NULL DEFAULT 0,
    -- Metadata
    is_system INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_style_presets_active ON style_presets(is_active);

-- ─── Remotion Render Jobs Table ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS remotion_renders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    clip_rank INTEGER NOT NULL,
    render_job_id TEXT DEFAULT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    progress REAL NOT NULL DEFAULT 0.0,
    current_frame INTEGER NOT NULL DEFAULT 0,
    total_frames INTEGER NOT NULL DEFAULT 0,
    output_path TEXT DEFAULT NULL,
    error_message TEXT DEFAULT NULL,
    render_time_seconds REAL DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT DEFAULT NULL,
    completed_at TEXT DEFAULT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_remotion_renders_job ON remotion_renders(job_id);
CREATE INDEX IF NOT EXISTS idx_remotion_renders_status ON remotion_renders(status);
CREATE INDEX IF NOT EXISTS idx_remotion_renders_job_clip ON remotion_renders(job_id, clip_rank);

-- ─── Hook Animations Table ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS hook_animations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT NULL,
    preview_url TEXT DEFAULT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─── Seed: Default Style Presets ─────────────────────────────────────────────

INSERT OR IGNORE INTO style_presets (id, name, description, primary_color, secondary_color, background_accent, typography_mood, hook_animation, energy_level, transition_style, subtitle_position, enable_threejs, enable_ai_layer, is_system) VALUES
    ('bold_black', 'Bold Black', 'Classic bold white text on dark background', '#ffffff', '#ffcc00', '#000000', 'bold_impact', 'fade_scale', 'medium', 'smooth', 'bottom', 0, 0, 1),
    ('neon_pop', 'Neon Pop', 'Vibrant neon colors with energetic animations', '#00ffcc', '#ff00ff', '#0a0a0a', 'playful', 'slide_up', 'high', 'kinetic', 'bottom', 1, 0, 1),
    ('cinematic_dark', 'Cinematic Dark', 'Dark cinematic mood with dramatic effects', '#e0e0e0', '#ff4444', '#0d0d0d', 'dramatic', 'fade_scale', 'low', 'smooth', 'bottom', 1, 1, 1),
    ('minimal_clean', 'Minimal Clean', 'Clean minimal style with subtle animations', '#333333', '#666666', '#ffffff', 'elegant_minimal', 'typewriter', 'low', 'smooth', 'center', 0, 0, 1),
    ('glitch_tech', 'Glitch Tech', 'Futuristic glitch effects for tech content', '#00ff00', '#ff0000', '#0a0a0a', 'bold_impact', 'glitch', 'high', 'kinetic', 'bottom', 1, 1, 1);

-- ─── Seed: Default Hook Animations ───────────────────────────────────────────

INSERT OR IGNORE INTO hook_animations (id, name, description) VALUES
    ('fade_scale', 'Fade & Scale', 'Text fades in with scale animation'),
    ('slide_up', 'Slide Up', 'Text slides up from bottom'),
    ('glitch', 'Glitch Effect', 'RGB glitch with digital distortion'),
    ('typewriter', 'Typewriter', 'Character-by-character reveal'),
    ('glitch_rgb', 'RGB Split', 'Separated red/cyan channels for fast tech moments'),
    ('shake_neon', 'Neon Shake', 'Electric glow with subtle jitter'),
    ('cinematic_reveal', 'Cinematic Reveal', 'Letterbox reveal for dramatic moments'),
    ('danger_bold', 'Danger Bold', 'Red alert typography with pulsing glow'),
    ('slide_punch_framer', 'Slide Punch', 'Fast slide-in with a punchy stop'),
    ('bold_slam', 'Bold Slam', 'Large impact card with a bounce entrance'),
    ('podcast_lower_third', 'On-Air Lower Third', 'Podcast-style lower third with live on-air badge'),
    ('quote_card', 'Quote Card', 'Editorial pull-quote card for memorable podcast lines'),
    ('waveform_pulse', 'Waveform Pulse', 'Audio waveform bars pulsing around the hook'),
    ('breaking_tape', 'Breaking Tape', 'Diagonal hot-take tape for spicy podcast moments'),
    ('mic_drop', 'Mic Drop', 'Impact badge drop with a bright hit line');


-- ═══════════════════════════════════════════════════════════════════════════════
-- v3.1 Premium Features & User Presets
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─── User Presets Table ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    hook_style JSON NOT NULL DEFAULT '{}',
    subtitle_style JSON NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_presets_user ON user_presets(user_id);

-- ─── User Features Table (Premium Access Control) ────────────────────────────

CREATE TABLE IF NOT EXISTS user_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    feature_code TEXT NOT NULL,
    granted_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, feature_code),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (granted_by) REFERENCES users(id)
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- v4.0 Reframe Tuning Configs (dynamic, no hardcoded constants)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS reframe_tuning_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER DEFAULT NULL,          -- NULL = global default, user_id = per-user override
    -- Sampling & Detection
    sample_interval_sec REAL NOT NULL DEFAULT 0.333,
    max_samples INTEGER NOT NULL DEFAULT 720,
    face_confidence REAL NOT NULL DEFAULT 0.55,
    min_face_size_ratio REAL NOT NULL DEFAULT 0.10,
    max_face_size_ratio REAL NOT NULL DEFAULT 0.50,
    min_separation_ratio REAL NOT NULL DEFAULT 0.20,
    min_coexist_ratio REAL NOT NULL DEFAULT 0.40,
    -- Auto Grid
    dominance_single_crop REAL NOT NULL DEFAULT 0.75,
    grid_base_zoom REAL NOT NULL DEFAULT 1.08,
    grid_max_zoom REAL NOT NULL DEFAULT 1.85,
    grid_face_margin REAL NOT NULL DEFAULT 0.35,
    grid_enter_samples INTEGER NOT NULL DEFAULT 9,
    grid_exit_samples INTEGER NOT NULL DEFAULT 6,
    min_grid_segment_seconds REAL NOT NULL DEFAULT 3.0,
    -- Ghost Detection
    min_face_area_px INTEGER NOT NULL DEFAULT 4000,
    min_area_ratio_to_max REAL NOT NULL DEFAULT 0.25,
    min_frame_ratio REAL NOT NULL DEFAULT 0.15,
    ghost_iou_threshold REAL NOT NULL DEFAULT 0.25,
    ghost_center_dist_ratio REAL NOT NULL DEFAULT 0.08,
    ghost_center_dist_broad REAL NOT NULL DEFAULT 0.20,
    min_pair_size_ratio REAL NOT NULL DEFAULT 0.18,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_features_user ON user_features(user_id);
CREATE INDEX IF NOT EXISTS idx_user_features_code ON user_features(feature_code);
