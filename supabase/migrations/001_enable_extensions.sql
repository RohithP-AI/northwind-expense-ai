-- Enable required Postgres extensions
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";
create extension if not exists "vector";        -- pgvector for embeddings
