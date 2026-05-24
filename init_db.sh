#!/bin/bash

DB_URL="postgresql://postgres:Postgres@100.107.186.61:5432/crypto_analyser"

echo "Creating table in the database..."
psql $DB_URL -f news_data/schema.sql
echo "Finished"
