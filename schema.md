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
 
 id        : afin de donner une identité unique en donnant un numéro de manière automatique 		       pour chaque nouvel news
 Title     : le titre est obligatoire
 Description : Certain news ne possède pas de description dans l'API
 Link      : toujours avoir le lien afin de vérifier la source et se documenter 
 Date      : Afin de s'adapter au fuseau horaire de la France
 Source    : Obligatoire pour vérifier l'info
 Catégorie : obligatoire pour mieux classer les articles
 Tickers   : créer une liste avec TEXT[] pour mieux filtrer les articles
 Combo     : " GENERATED ALWAYS AS (....) permet de générer automatiquement un modele 			     d'affichage, " || " permet de regrouper , COALESCE ('nom_colonne',                             	     'message_erreur') permet de remplacer la valeur si NUL et STORED pour 	 
	     indexer et évite la  répétition
 Research  : tsvector fonction qui permet de prêt macher les mots afin d'obtenir des mots clés 		     facilitant la recherche, on saisi la langue et la combinaison.
 AI      : pour le embidding, le script python s'en charge
  
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
combo TEXT GENERATED ALWAYS AS (Title || ' ' || COALESCE(Description, '' )) STORED, OK
research tsvector GENERATED ALWAYS AS (to_tsvector('english', Title || ' ' || COALESCE(Description, ''))) STORED
sentiment VARCHAR(7) NULL,
timeago TEXT NOT NULL 
);
**
