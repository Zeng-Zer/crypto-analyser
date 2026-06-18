-- news_data/schema.sql
CREATE EXTENSION IF NOT EXISTS vector; 

CREATE TABLE IF NOT EXISTS crypto_news(
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    link TEXT NOT NULL,
    date_pub TIMESTAMPTZ,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    tickers TEXT[] NOT NULL,
    title_description TEXT GENERATED ALWAYS AS (title || ' ' || COALESCE(description, '' )) STORED,
    research tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || COALESCE(description, ''))) STORED,
    sentiment VARCHAR(7) NULL,
<<<<<<< HEAD
    UNIQUE(link, date_pub)
    
    );
=======
    timeago TEXT NOT NULL
);
>>>>>>> de1d714 (rename combo column to title_description)
