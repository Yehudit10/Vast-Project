CREATE OR REPLACE FUNCTION fn_similar(p_id BIGINT, p_k INT DEFAULT 10)
RETURNS TABLE (id BIGINT, distance real)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  qvec vector(384);
BEGIN
  SELECT e.vec INTO qvec FROM embeddings e WHERE e.id = p_id;
  IF qvec IS NULL THEN
    RAISE EXCEPTION 'fn_similar: id % not found', p_id;
  END IF;

  RETURN QUERY
    SELECT i.id, (i.vec <-> qvec)::real AS distance 
    FROM embeddings i
    WHERE i.id <> p_id
    ORDER BY i.vec <-> qvec
    LIMIT p_k;
END;
$$;
