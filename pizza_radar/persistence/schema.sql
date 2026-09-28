-- Esquema relacional canónico do Pizza Radar PT (Dialeto SQLite / libSQL)

CREATE TABLE IF NOT EXISTS stores (
    store_id TEXT PRIMARY KEY,
    vendor TEXT NOT NULL,
    name TEXT NOT NULL,
    postal_code TEXT,
    address TEXT,
    is_lisbon_municipality BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS promotions (
    id TEXT PRIMARY KEY,
    vendor TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    price_cents INTEGER,
    original_price_cents INTEGER,
    discount_percentage REAL,
    discount_type TEXT NOT NULL,
    store_scope TEXT NOT NULL,
    pizza_count INTEGER,
    pizza_size TEXT,
    conditions TEXT,
    valid_from TIMESTAMP,
    valid_until TIMESTAMP,
    observed_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NOT NULL,
    consecutive_misses INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    location_scope TEXT NOT NULL DEFAULT 'Lisboa',
    source_url TEXT,
    image_url TEXT,
    raw_payload_json TEXT
);

CREATE TABLE IF NOT EXISTS promotion_stores (
    promotion_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    PRIMARY KEY (promotion_id, store_id),
    FOREIGN KEY (promotion_id) REFERENCES promotions(id) ON DELETE CASCADE,
    FOREIGN KEY (store_id) REFERENCES stores(store_id)
);

CREATE TABLE IF NOT EXISTS observation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    promotion_id TEXT NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    price_cents INTEGER,
    original_price_cents INTEGER,
    is_available BOOLEAN NOT NULL,
    FOREIGN KEY (promotion_id) REFERENCES promotions(id)
);

CREATE TABLE IF NOT EXISTS vendor_sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor TEXT NOT NULL,
    status TEXT NOT NULL,
    offers_found INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    executed_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_promotions_active ON promotions(is_active, vendor);
CREATE INDEX IF NOT EXISTS idx_promotions_observed ON promotions(observed_at);
CREATE INDEX IF NOT EXISTS idx_history_promo ON observation_history(promotion_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_sync_vendor ON vendor_sync_runs(vendor, executed_at);
