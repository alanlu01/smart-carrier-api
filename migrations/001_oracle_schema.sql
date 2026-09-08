-- Smart Carrier schema for Oracle Autonomous AI Database.
-- Statements are separated by a slash so app.migrations can execute them safely.

BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE locations (
      code VARCHAR2(32) PRIMARY KEY,
      name VARCHAR2(200) NOT NULL,
      description VARCHAR2(1000),
      floor VARCHAR2(50),
      x NUMBER,
      y NUMBER,
      yaw NUMBER,
      enabled NUMBER(1) DEFAULT 1 NOT NULL CHECK (enabled IN (0, 1)),
      created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
    )
  ]';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE locations ADD (enabled NUMBER(1) DEFAULT 1 NOT NULL CHECK (enabled IN (0, 1)))';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE tasks (
      id VARCHAR2(36) PRIMARY KEY,
      location_code VARCHAR2(32) NOT NULL REFERENCES locations(code),
      task_type VARCHAR2(32) NOT NULL,
      status VARCHAR2(20) DEFAULT 'pending' NOT NULL,
      note VARCHAR2(500),
      result_note VARCHAR2(500),
      power_bank_id VARCHAR2(64),
      required_charge NUMBER(3),
      quantity NUMBER(1) DEFAULT 1 NOT NULL,
      robot_id VARCHAR2(64),
      created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      updated_at TIMESTAMP WITH TIME ZONE,
      assigned_at TIMESTAMP WITH TIME ZONE,
      completed_at TIMESTAMP WITH TIME ZONE,
      cancel_requested_at TIMESTAMP WITH TIME ZONE,
      cancel_reason VARCHAR2(500),
      warning NUMBER(1) DEFAULT 0 NOT NULL,
      progress_state VARCHAR2(32),
      progress_message VARCHAR2(500),
      expected_slot NUMBER(1),
      changed_slot NUMBER(1),
      changed_slots VARCHAR2(32),
      action_deadline TIMESTAMP WITH TIME ZONE,
      progress_event_id VARCHAR2(36),
      progress_updated_at TIMESTAMP WITH TIME ZONE,
      CONSTRAINT ck_tasks_type CHECK (
        task_type IN ('borrow', 'return', 'delivery', 'navigation', 'callbot')
      ),
      CONSTRAINT ck_tasks_status CHECK (
        status IN ('pending', 'in_progress', 'done', 'cancelled', 'failed')
      ),
      CONSTRAINT ck_tasks_charge CHECK (
        required_charge IS NULL OR required_charge BETWEEN 0 AND 100
      ),
      CONSTRAINT ck_tasks_quantity CHECK (quantity BETWEEN 1 AND 3)
    )
  ]';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD (power_bank_id VARCHAR2(64))';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD (cancel_requested_at TIMESTAMP WITH TIME ZONE)';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD (cancel_reason VARCHAR2(500))';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE robots (
      id VARCHAR2(64) PRIMARY KEY,
      robot_mode VARCHAR2(32) DEFAULT 'idle' NOT NULL,
      battery NUMBER,
      location_code VARCHAR2(32) REFERENCES locations(code) ON DELETE SET NULL,
      x NUMBER,
      y NUMBER,
      yaw NUMBER,
      last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      CONSTRAINT ck_robots_battery CHECK (battery IS NULL OR battery BETWEEN 0 AND 100)
    )
  ]';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE power_slots (
      robot_id VARCHAR2(64) NOT NULL REFERENCES robots(id) ON DELETE CASCADE,
      slot_number NUMBER(1) NOT NULL,
      bank_id VARCHAR2(64),
      status VARCHAR2(32) DEFAULT 'empty' NOT NULL,
      enabled NUMBER(1) DEFAULT 1 NOT NULL,
      current_amps NUMBER,
      voltage_volts NUMBER,
      charge NUMBER,
      sensor_ok NUMBER(1) DEFAULT 1 NOT NULL CHECK (sensor_ok IN (0, 1)),
      updated_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      CONSTRAINT pk_power_slots PRIMARY KEY (robot_id, slot_number),
      CONSTRAINT ck_slot_number CHECK (slot_number BETWEEN 1 AND 3),
      CONSTRAINT ck_slot_charge CHECK (charge IS NULL OR charge BETWEEN 0 AND 100)
    )
  ]';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

-- Keep an already deployed database upgradeable with the same idempotent migration.
BEGIN
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD warning NUMBER(1) DEFAULT 0 NOT NULL';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD progress_state VARCHAR2(32)';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD progress_message VARCHAR2(500)';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD expected_slot NUMBER(1)';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD changed_slot NUMBER(1)';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD changed_slots VARCHAR2(32)';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD action_deadline TIMESTAMP WITH TIME ZONE';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD progress_event_id VARCHAR2(36)';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE tasks ADD progress_updated_at TIMESTAMP WITH TIME ZONE';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE power_slots ADD enabled NUMBER(1) DEFAULT 1 NOT NULL';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE power_slots ADD sensor_ok NUMBER(1) DEFAULT 1 NOT NULL CHECK (sensor_ok IN (0, 1))';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE power_slots ADD voltage_volts NUMBER';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE power_slots ADD current_amps NUMBER';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  BEGIN EXECUTE IMMEDIATE 'ALTER TABLE power_slots ADD charge NUMBER';
  EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF; END;
  UPDATE power_slots SET enabled = 0 WHERE status = 'disabled' AND enabled != 0;
END;
/

BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE robot_events (
      id VARCHAR2(36) PRIMARY KEY,
      robot_id VARCHAR2(64) NOT NULL REFERENCES robots(id) ON DELETE CASCADE,
      task_id VARCHAR2(36) REFERENCES tasks(id) ON DELETE SET NULL,
      event_type VARCHAR2(64) NOT NULL,
      payload CLOB DEFAULT '{}' NOT NULL CHECK (payload IS JSON),
      created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
    )
  ]';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_tasks_status_created ON tasks(status, created_at)';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_events_robot_created ON robot_events(robot_id, created_at)';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

MERGE INTO locations target
USING (
  SELECT 'A1' code, '右樓梯口' name, '3F' floor, 7.7 x, -7.2 y, 0 yaw FROM dual
) source
ON (target.code = source.code)
WHEN MATCHED THEN UPDATE SET
  target.name = source.name, target.floor = source.floor,
  target.x = source.x, target.y = source.y, target.yaw = source.yaw, target.enabled = 1
WHEN NOT MATCHED THEN INSERT (code, name, floor, x, y, yaw, enabled)
VALUES (source.code, source.name, source.floor, source.x, source.y, source.yaw, 1);
/

MERGE INTO locations target
USING (
  SELECT 'E1' code, '左樓梯口' name, '3F' floor, 7 x, 5.5 y, 0 yaw FROM dual
) source
ON (target.code = source.code)
WHEN MATCHED THEN UPDATE SET
  target.name = source.name, target.floor = source.floor,
  target.x = source.x, target.y = source.y, target.yaw = source.yaw, target.enabled = 1
WHEN NOT MATCHED THEN INSERT (code, name, floor, x, y, yaw, enabled)
VALUES (source.code, source.name, source.floor, source.x, source.y, source.yaw, 1);
/

MERGE INTO locations target
USING (
  SELECT 'F1' code, '電機工程學系' name, '3F' floor, -2.6 x, 4.7 y, 0 yaw FROM dual
) source
ON (target.code = source.code)
WHEN MATCHED THEN UPDATE SET
  target.name = source.name, target.floor = source.floor,
  target.x = source.x, target.y = source.y, target.yaw = source.yaw, target.enabled = 1
WHEN NOT MATCHED THEN INSERT (code, name, floor, x, y, yaw, enabled)
VALUES (source.code, source.name, source.floor, source.x, source.y, source.yaw, 1);
/

UPDATE locations SET enabled = 0 WHERE code = 'S1';
/
