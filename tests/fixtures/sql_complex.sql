-- Schema and views
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    total NUMERIC(12, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX idx_orders_user ON orders(user_id);

CREATE INDEX idx_orders_status ON orders(status);

CREATE VIEW active_users AS
    SELECT id, email, name
    FROM users
    WHERE created_at > NOW() - INTERVAL '30 days';

-- CTEs and complex SELECTs
WITH monthly_totals AS (
    SELECT user_id, DATE_TRUNC('month', created_at) AS month, SUM(total) AS total
    FROM orders
    WHERE status = 'paid'
    GROUP BY user_id, month
)
SELECT u.name, m.month, m.total
FROM users u
JOIN monthly_totals m ON m.user_id = u.id
ORDER BY m.total DESC
LIMIT 50;

SELECT u.id,
       u.name,
       (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS order_count
FROM users u
WHERE u.created_at > NOW() - INTERVAL '1 year';

SELECT user_id, AVG(total) AS avg_total
FROM orders
GROUP BY user_id
HAVING AVG(total) > 100.0;

-- Functions (stored procedures expressed as create_function)
CREATE FUNCTION user_lifetime_value(uid BIGINT) RETURNS NUMERIC AS $$
    SELECT COALESCE(SUM(total), 0) FROM orders WHERE user_id = uid
$$ LANGUAGE sql;

CREATE FUNCTION top_customers(n INT) RETURNS TABLE(user_id BIGINT, total NUMERIC) AS $$
    SELECT user_id, SUM(total) AS total
    FROM orders
    GROUP BY user_id
    ORDER BY total DESC
    LIMIT n
$$ LANGUAGE sql;
