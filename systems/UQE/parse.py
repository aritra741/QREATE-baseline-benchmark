from plan import planner
import logging
import sys

# Setup logger
logger = logging.getLogger('UQE.parse')
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[UQE-PARSE] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

def split_query(query):
    parts = []
    start = query.find('SELECT')
    end = query.find('FROM')
    select_clause = query[start+7:end].split(',')
    select_clause = [clause.strip() for clause in select_clause]
    parts.append(select_clause)

    start = query.find('FROM')
    end = query.find('WHERE')
    if end == -1:
        end = query.find('GROUP BY')
        if end == -1:
            end = query.find('ORDER BY')
            if end == -1:
                end = query.find('LIMIT')
                if end == -1:
                    end = len(query)
    from_clause = query[start+5:end].split(',')
    from_clause = [t.strip() for t in from_clause]
    parts.append(from_clause)

    start = query.find('WHERE')
    if start == -1:
        parts.append([])
    else:
        end = query.find('GROUP BY')
        if end == -1:
            end = query.find('ORDER BY')
            if end == -1:
                end = query.find('LIMIT')
                if end == -1:
                    end = len(query)
        parts.append(query[start+6:end].strip())
    
    start = query.find('GROUP BY')
    if start == -1:
        parts.append([])
    else:
        end = query.find('HAVING')
        if end == -1:
            end = query.find('ORDER BY')
            if end == -1:
                end = query.find('LIMIT')
                if end == -1:
                    end = len(query)
        group_by_clause = query[start+9:end].split(',')
        group_by_clause = [g.strip() for g in group_by_clause]
        parts.append(group_by_clause)
    
    start = query.find('ORDER BY')
    if start == -1:
        parts.append([])
    else:
        end = query.find('LIMIT')
        if end == -1:
            end = len(query)
        order_by_clause = query[start+9:end].split(',')
        order_by_clause = [o.strip() for o in order_by_clause]
        parts.append(order_by_clause)
    
    start = query.find('LIMIT')
    if start == -1:
        parts.append([])
    else:
        limit_clause = query[start+6:].split(',')
        limit_clause = [l.strip() for l in limit_clause]
        parts.append(limit_clause)

    return parts

def parser(query):
    logger.info("=" * 60)
    logger.info("Parsing SQL query")
    logger.info("=" * 60)
    logger.debug(f"Input query: {query}")
    
    query = query.rstrip(';')
    logger.debug(f"Query after stripping semicolon: {query}")
    
    parts = split_query(query)
    
    logger.info("Query parsed into parts:")
    logger.info(f"  SELECT: {parts[0]}")
    logger.info(f"  FROM: {parts[1]}")
    logger.info(f"  WHERE: {parts[2] if parts[2] else 'None'}")
    logger.info(f"  GROUP BY: {parts[3] if parts[3] else 'None'}")
    logger.info(f"  ORDER BY: {parts[4] if parts[4] else 'None'}")
    logger.info(f"  LIMIT: {parts[5] if parts[5] else 'None'}")

    return parts
