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
      created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
    )
  ]';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
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
      voltage_volts NUMBER,
      current_amps NUMBER,
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

BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE power_slots ADD (voltage_volts NUMBER)';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE q'[
    ALTER TABLE power_slots ADD (
      sensor_ok NUMBER(1) DEFAULT 1 NOT NULL CHECK (sensor_ok IN (0, 1))
    )
  ]';
EXCEPTION
  WHEN OTHERS THEN IF SQLCODE != -1430 THEN RAISE; END IF;
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
  SELECT 'A1' code, '門口' name, '1F' floor, -0.45 x, -0.35 y, 0 yaw FROM dual
) source
ON (target.code = source.code)
WHEN NOT MATCHED THEN INSERT (code, name, floor, x, y, yaw)
VALUES (source.code, source.name, source.floor, source.x, source.y, source.yaw);
/

MERGE INTO locations target
USING (
  SELECT 'F1' code, '廁所' name, '1F' floor, -4 x, 1.5 y, 3.14 yaw FROM dual
) source
ON (target.code = source.code)
WHEN NOT MATCHED THEN INSERT (code, name, floor, x, y, yaw)
VALUES (source.code, source.name, source.floor, source.x, source.y, source.yaw);
/

MERGE INTO locations target
USING (
  SELECT 'E1' code, '廚房' name, '1F' floor, -1.5 x, 5 y, 0 yaw FROM dual
) source
ON (target.code = source.code)
WHEN NOT MATCHED THEN INSERT (code, name, floor, x, y, yaw)
VALUES (source.code, source.name, source.floor, source.x, source.y, source.yaw);
/

MERGE INTO locations target
USING (
  SELECT 'S1' code, '客廳TV' name, '1F' floor, 0.4 x, 0 y, 0 yaw FROM dual
) source
ON (target.code = source.code)
WHEN NOT MATCHED THEN INSERT (code, name, floor, x, y, yaw)
VALUES (source.code, source.name, source.floor, source.x, source.y, source.yaw);
/
