import logging
import sys

# Setup logger
logger = logging.getLogger('UQE.execute')
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[UQE-EXECUTE] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

def executor(plan_oper):
    logger.info("=" * 60)
    logger.info("Starting query execution")
    logger.info("=" * 60)
    
    try:
        logger.debug("Calling plan_oper.next() to execute query plan")
        df = plan_oper.next()
        
        if df is not None:
            logger.info(f"Query execution completed successfully")
            logger.info(f"Result shape: {df.shape} (rows={len(df)}, cols={len(df.columns)})")
            logger.info(f"Result columns: {list(df.columns)}")
            if len(df) > 0:
                logger.debug(f"First few rows:\n{df.head(3).to_string()}")
            else:
                logger.warning("Result DataFrame is EMPTY - no rows returned")
        else:
            logger.warning("Query execution returned None")
        
        return df
    except Exception as e:
        logger.error(f"Query execution failed: {e}", exc_info=True)
        raise