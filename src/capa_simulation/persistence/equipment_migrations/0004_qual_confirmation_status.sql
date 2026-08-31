ALTER TABLE equipment_ops.equipment_master_snapshot
ADD COLUMN qual_confirmation_status VARCHAR;

UPDATE equipment_ops.equipment_master_snapshot
SET qual_confirmation_status = '계획'
WHERE qual_date IS NOT NULL;
