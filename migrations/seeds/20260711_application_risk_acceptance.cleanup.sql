-- 清理 Iteration 2B.2 合成申请数据，只删除 A1024、A1058、A1091 对应记录。

START TRANSACTION;

DELETE FROM application_material_item
 WHERE application_id IN (1024, 1058, 1091)
   AND material_name LIKE 'ITER2B2_TEST_%';

COMMIT;

