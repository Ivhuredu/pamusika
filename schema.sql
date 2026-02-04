CREATE TABLE sellers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    location TEXT
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    price TEXT,
    seller_id INTEGER REFERENCES sellers(id)
);
