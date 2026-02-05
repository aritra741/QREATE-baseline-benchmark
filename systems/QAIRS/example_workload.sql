-- Example SQL Workload for QAIRS MQO Testing
-- This file demonstrates queries that can be optimized through sibling merging

-- Query 1: Find all denied claims
SELECT * FROM claims WHERE status = 'Denied';

-- Query 2: Find all paid claims
SELECT * FROM claims WHERE status = 'Paid';

-- Query 3: Find high-cost claims
SELECT * FROM claims WHERE cost > 1000;

-- Query 4: Find claims from specific insurer
SELECT * FROM claims WHERE insurer = 'Cigna';

-- Query 5: Find all approved claims
SELECT * FROM claims WHERE status = 'Approved';

-- Query 6: Complex query with multiple conditions
SELECT * FROM claims WHERE status = 'Denied' AND cost > 5000;

-- Query 7: Find all claims (no filter)
SELECT * FROM claims;

-- Expected Optimization:
-- - Q1, Q2, Q5 should be merged into: status IN ('Denied', 'Paid', 'Approved')
-- - Q3, Q6 might be optimized based on range subsumption
-- - Q7 subsumes all other queries (if executed, satisfies everything)
