#!/bin/bash

echo "Creating table in the database...""
DB_URL=$(grep "^DATABASE_URL=" .env | cut -d '=' -f 2-)
psql "$DB_URL" -f news_data/schema.sql
echo "Finished."
