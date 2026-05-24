# Data type

- Id : int, primary key, serial
- Title : text, not null,
- Description : TEXT
- Link : TEXT,  not null, unique
- Date : TIMESTAMPTZ
- Source : TEXT, not null
- Category : TEXT,not null
- Tickers : TEXT [], not null
- Combo : TEXT, GENERATED ALWAYS AS (title || '	' || COALESCE(description, '	'))  STORED	
- Research : tsvector(to_tsvector('English', 'GENERATED ALWAYS AS (title || '	' || COALESCE(description, '	')')) STORED
- AI : vector(1536)

# Documentation

**
id: used to provide a unique identity by automatically assigning a number to each new news item.
Title: the title is mandatory.
Description: some news items do not have a description in the API.
Link: always keep the link in order to verify the source and get more information.
Date: adapted to the French time zone.
Source: mandatory to verify the information.
Category: mandatory to better classify the articles.
Tickers: create a TEXT[] list to better filter the articles.
Combo: GENERATED ALWAYS AS (...) automatically generates a display model, || is used to concatenate values, COALESCE('column_name', 'error_message') replaces the value when it is NULL, and STORED allows indexing and avoids repetition.
Research: tsvector function used to preprocess words in order to generate keywords that make searching easier; the language and combination are specified.
AI: used for embeddings; the Python script handles it.
  
**

# Schema structure

**

CREATE DATABASE crypto_analyser;
CREATE EXTENSION IF NOT EXISTS vector; 
CREATE TABLE crypto_news(
id SERIAL PRIMARY KEY,
title TEXT NOT NULL, 
description TEXT,
link TEXT NOT NULL UNIQUE, 
date_pub TIMESTAMPTZ, 
source TEXT NOT NULL,
category TEXT NOT NULL, 
tickers TEXT[] NOT NULL,
combo TEXT GENERATED ALWAYS AS (Title || ' ' || COALESCE(Description, '' )) ,
research tsvector GENERATED ALWAYS AS (to_tsvector('english', Title || ' ' || COALESCE(Description, '')))
sentiment VARCHAR(7) NULL
);
**

