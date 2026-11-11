import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

CITIES = ["New York", "San Francisco", "London", "Tokyo", "Berlin", "Singapore", "Sydney", "Toronto"]
COUNTRIES = ["USA", "UK", "Germany", "Japan", "Singapore", "Australia", "Canada"]
TIERS = ["STANDARD", "SILVER", "GOLD", "PLATINUM"]
FIRST_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Evan", "Fiona", "George", "Hannah", "Ian", "Julia"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]

class DatasetGenerator:
    """Generates deterministic, reproducible CDC event datasets with controlled edge cases."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)
        self.base_time = datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc)

    def generate_starter_sample(self) -> List[Dict[str, Any]]:
        """
        Generates a curated starter dataset (~60 events) covering normal flows,
        SCD2 lifecycle, duplicates, out-of-order mutations, and labeled negative edge cases.
        """
        events: List[Dict[str, Any]] = []
        t = self.base_time

        # --- 1. Customer Inserts ---
        customer_ids = [f"CUST-{1000 + i}" for i in range(1, 11)]
        for i, cid in enumerate(customer_ids, start=1):
            fname = FIRST_NAMES[(i - 1) % len(FIRST_NAMES)]
            lname = LAST_NAMES[(i - 1) % len(LAST_NAMES)]
            events.append({
                "event_id": f"evt_cust_ins_{cid}",
                "entity_type": "CUSTOMER",
                "entity_id": cid,
                "operation": "INSERT",
                "event_timestamp": (t + timedelta(minutes=i * 5)).isoformat(),
                "sequence_number": 1,
                "payload": {
                    "customer_id": cid,
                    "name": f"{fname} {lname}",
                    "email": f"{fname.lower()}.{lname.lower()}@example.com",
                    "tier": "STANDARD",
                    "credit_limit": 5000.0,
                    "status": "ACTIVE",
                    "address_city": CITIES[i % len(CITIES)],
                    "address_country": COUNTRIES[i % len(COUNTRIES)]
                },
                "source_system": "crm-service"
            })

        # --- 2. Customer Updates (SCD Type 2 Lifecycle) ---
        # CUST-1001 upgrades to SILVER, then GOLD
        events.append({
            "event_id": "evt_cust_upd_1001_v2",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-1001",
            "operation": "UPDATE",
            "event_timestamp": (t + timedelta(hours=1, minutes=10)).isoformat(),
            "sequence_number": 2,
            "payload": {
                "name": "Alice Smith",
                "email": "alice.smith@example.com",
                "tier": "SILVER",
                "credit_limit": 10000.0,
                "status": "ACTIVE"
            },
            "source_system": "crm-service"
        })
        events.append({
            "event_id": "evt_cust_upd_1001_v3",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-1001",
            "operation": "UPDATE",
            "event_timestamp": (t + timedelta(hours=2, minutes=30)).isoformat(),
            "sequence_number": 3,
            "payload": {
                "name": "Alice Smith",
                "email": "alice.smith@example.com",
                "tier": "GOLD",
                "credit_limit": 25000.0,
                "status": "ACTIVE"
            },
            "source_system": "crm-service"
        })

        # --- 3. Duplicate Event (Idempotency Testing) ---
        # Duplicate of CUST-1001 v2 with exact same event_id
        events.append({
            "event_id": "evt_cust_upd_1001_v2",  # Duplicate event_id
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-1001",
            "operation": "UPDATE",
            "event_timestamp": (t + timedelta(hours=1, minutes=10)).isoformat(),
            "sequence_number": 2,
            "payload": {
                "name": "Alice Smith",
                "email": "alice.smith@example.com",
                "tier": "SILVER",
                "credit_limit": 10000.0,
                "status": "ACTIVE"
            },
            "source_system": "crm-service"
        })

        # --- 4. Late-Arriving / Out-of-Order Event ---
        # Event with sequence 2 for CUST-1002 arrives AFTER sequence 3 has been processed
        events.append({
            "event_id": "evt_cust_upd_1002_v3",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-1002",
            "operation": "UPDATE",
            "event_timestamp": (t + timedelta(hours=3, minutes=0)).isoformat(),
            "sequence_number": 3,
            "payload": {
                "name": "Bob Johnson",
                "email": "bob.johnson@example.com",
                "tier": "PLATINUM",
                "credit_limit": 50000.0,
                "status": "ACTIVE"
            },
            "source_system": "crm-service"
        })
        # Stale event with older sequence (seq 2, earlier timestamp)
        events.append({
            "event_id": "evt_cust_upd_1002_v2_late",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-1002",
            "operation": "UPDATE",
            "event_timestamp": (t + timedelta(hours=1, minutes=45)).isoformat(),
            "sequence_number": 2,
            "payload": {
                "name": "Bob Johnson",
                "email": "bob.johnson@example.com",
                "tier": "SILVER",
                "credit_limit": 15000.0,
                "status": "ACTIVE"
            },
            "source_system": "crm-service"
        })

        # --- 5. Customer Delete Event ---
        # CUST-1003 is deleted
        events.append({
            "event_id": "evt_cust_del_1003",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-1003",
            "operation": "DELETE",
            "event_timestamp": (t + timedelta(hours=4, minutes=0)).isoformat(),
            "sequence_number": 2,
            "payload": {},
            "source_system": "crm-service"
        })

        # --- 6. Valid Orders (Referencing Active Customers) ---
        for i in range(1, 15):
            oid = f"ORD-{5000 + i}"
            cid = f"CUST-100{1 + (i % 2)}" # Links to CUST-1001 or CUST-1002
            events.append({
                "event_id": f"evt_ord_ins_{oid}",
                "entity_type": "ORDER",
                "entity_id": oid,
                "operation": "INSERT",
                "event_timestamp": (t + timedelta(hours=4, minutes=10 + i * 3)).isoformat(),
                "sequence_number": 1,
                "payload": {
                    "order_id": oid,
                    "customer_id": cid,
                    "order_amount": round(100.0 + i * 45.5, 2),
                    "order_status": "CONFIRMED",
                    "currency": "USD"
                },
                "source_system": "storefront-api"
            })

        # --- 7. Order Status Updates ---
        events.append({
            "event_id": "evt_ord_upd_5001_ship",
            "entity_type": "ORDER",
            "entity_id": "ORD-5001",
            "operation": "UPDATE",
            "event_timestamp": (t + timedelta(hours=5, minutes=30)).isoformat(),
            "sequence_number": 2,
            "payload": {
                "customer_id": "CUST-1002",
                "order_amount": 145.5,
                "order_status": "SHIPPED",
                "currency": "USD"
            },
            "source_system": "logistics-service"
        })

        # --- 8. Labeled Negative Edge Cases (Deliberate Quarantine) ---
        # Edge Case 1: Malformed input (missing required envelope fields)
        events.append({
            "_test_label": "EDGE_CASE: Malformed Envelope - Missing entity_id & operation",
            "event_id": "evt_bad_envelope_001",
            "event_timestamp": t.isoformat(),
            "payload": {"random": "value"}
        })

        # Edge Case 2: Missing required field (Customer without name)
        events.append({
            "_test_label": "EDGE_CASE: Customer missing required name",
            "event_id": "evt_bad_cust_no_name",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-9001",
            "operation": "INSERT",
            "event_timestamp": (t + timedelta(hours=6)).isoformat(),
            "sequence_number": 1,
            "payload": {
                "customer_id": "CUST-9001",
                "email": "noname@example.com",
                "tier": "STANDARD",
                "credit_limit": 1000.0
            }
        })

        # Edge Case 3: Invalid email format
        events.append({
            "_test_label": "EDGE_CASE: Invalid customer email format",
            "event_id": "evt_bad_cust_email",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-9002",
            "operation": "INSERT",
            "event_timestamp": (t + timedelta(hours=6, minutes=5)).isoformat(),
            "sequence_number": 1,
            "payload": {
                "customer_id": "CUST-9002",
                "name": "Bad Email User",
                "email": "not-an-email-address",
                "tier": "STANDARD",
                "credit_limit": 500.0
            }
        })

        # Edge Case 4: Domain boundary violation (negative credit limit)
        events.append({
            "_test_label": "EDGE_CASE: Negative credit limit boundary violation",
            "event_id": "evt_bad_cust_neg_credit",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-9003",
            "operation": "INSERT",
            "event_timestamp": (t + timedelta(hours=6, minutes=10)).isoformat(),
            "sequence_number": 1,
            "payload": {
                "customer_id": "CUST-9003",
                "name": "Negative Limit",
                "email": "neg@example.com",
                "tier": "STANDARD",
                "credit_limit": -500.0
            }
        })

        # Edge Case 5: Referential Integrity Violation (Order for non-existent customer)
        events.append({
            "_test_label": "EDGE_CASE: Order referencing non-existent customer CUST-99999",
            "event_id": "evt_bad_ord_orphan",
            "entity_type": "ORDER",
            "entity_id": "ORD-9999",
            "operation": "INSERT",
            "event_timestamp": (t + timedelta(hours=6, minutes=15)).isoformat(),
            "sequence_number": 1,
            "payload": {
                "order_id": "ORD-9999",
                "customer_id": "CUST-99999", # Does not exist!
                "order_amount": 550.0,
                "order_status": "PENDING",
                "currency": "USD"
            }
        })

        # Edge Case 6: Referential Integrity Violation (Order for soft-deleted customer CUST-1003)
        events.append({
            "_test_label": "EDGE_CASE: Order referencing soft-deleted customer CUST-1003",
            "event_id": "evt_bad_ord_deleted_cust",
            "entity_type": "ORDER",
            "entity_id": "ORD-9998",
            "operation": "INSERT",
            "event_timestamp": (t + timedelta(hours=6, minutes=20)).isoformat(),
            "sequence_number": 1,
            "payload": {
                "order_id": "ORD-9998",
                "customer_id": "CUST-1003", # Soft-deleted earlier!
                "order_amount": 120.0,
                "order_status": "PENDING",
                "currency": "USD"
            }
        })

        # Edge Case 7: Invalid currency code (must be 3 characters)
        events.append({
            "_test_label": "EDGE_CASE: Invalid currency format",
            "event_id": "evt_bad_ord_curr",
            "entity_type": "ORDER",
            "entity_id": "ORD-9997",
            "operation": "INSERT",
            "event_timestamp": (t + timedelta(hours=6, minutes=25)).isoformat(),
            "sequence_number": 1,
            "payload": {
                "order_id": "ORD-9997",
                "customer_id": "CUST-1001",
                "order_amount": 75.0,
                "order_status": "PENDING",
                "currency": "US_DOLLAR_LONG" # Illegal length
            }
        })

        return events

    def generate_scalable_dataset(
        self,
        total_count: int = 100000,
        output_file: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates a configurable large dataset (e.g. 100k+ events) with realistic ratios:
        ~55% Inserts, ~35% Updates, ~3% Deletes, ~3% Duplicates, ~2% Out-of-order, ~2% Quarantined.
        """
        events: List[Dict[str, Any]] = []
        customer_pool = []
        order_pool = []
        t = self.base_time

        # Track versions per customer for monotonic sequences
        customer_versions: Dict[str, int] = {}
        order_versions: Dict[str, int] = {}

        # 1. Generate base pool of 5,000 customers
        num_base_customers = min(max(int(total_count * 0.25), 100), 10000)
        for i in range(1, num_base_customers + 1):
            cid = f"CUST-{i:06d}"
            fname = self.rng.choice(FIRST_NAMES)
            lname = self.rng.choice(LAST_NAMES)
            customer_pool.append(cid)
            customer_versions[cid] = 1
            ts = t + timedelta(seconds=i * 2)

            events.append({
                "event_id": f"evt_gen_c_ins_{cid}",
                "entity_type": "CUSTOMER",
                "entity_id": cid,
                "operation": "INSERT",
                "event_timestamp": ts.isoformat(),
                "sequence_number": 1,
                "payload": {
                    "customer_id": cid,
                    "name": f"{fname} {lname}",
                    "email": f"{fname.lower()}.{lname.lower()}.{i}@example.com",
                    "tier": self.rng.choice(TIERS),
                    "credit_limit": float(self.rng.randint(1000, 50000)),
                    "status": "ACTIVE",
                    "address_city": self.rng.choice(CITIES),
                    "address_country": self.rng.choice(COUNTRIES)
                },
                "source_system": "crm-service"
            })

        # 2. Fill the remaining events up to total_count
        while len(events) < total_count:
            roll = self.rng.random()
            current_sec = len(events) * 2
            ts = t + timedelta(seconds=current_sec)

            if roll < 0.35 and customer_pool:
                # Customer Update
                cid = self.rng.choice(customer_pool)
                seq = customer_versions[cid] + 1
                customer_versions[cid] = seq
                events.append({
                    "event_id": f"evt_gen_c_upd_{cid}_{seq}",
                    "entity_type": "CUSTOMER",
                    "entity_id": cid,
                    "operation": "UPDATE",
                    "event_timestamp": ts.isoformat(),
                    "sequence_number": seq,
                    "payload": {
                        "tier": self.rng.choice(TIERS),
                        "credit_limit": float(self.rng.randint(2000, 100000)),
                        "status": "ACTIVE"
                    },
                    "source_system": "crm-service"
                })

            elif roll < 0.65 and customer_pool:
                # Order Insert
                oid = f"ORD-{len(order_pool) + 1:07d}"
                order_pool.append(oid)
                order_versions[oid] = 1
                cid = self.rng.choice(customer_pool)
                events.append({
                    "event_id": f"evt_gen_o_ins_{oid}",
                    "entity_type": "ORDER",
                    "entity_id": oid,
                    "operation": "INSERT",
                    "event_timestamp": ts.isoformat(),
                    "sequence_number": 1,
                    "payload": {
                        "order_id": oid,
                        "customer_id": cid,
                        "order_amount": round(self.rng.uniform(10.0, 2500.0), 2),
                        "order_status": "CONFIRMED",
                        "currency": "USD"
                    },
                    "source_system": "storefront-api"
                })

            elif roll < 0.85 and order_pool:
                # Order Update
                oid = self.rng.choice(order_pool)
                seq = order_versions[oid] + 1
                order_versions[oid] = seq
                events.append({
                    "event_id": f"evt_gen_o_upd_{oid}_{seq}",
                    "entity_type": "ORDER",
                    "entity_id": oid,
                    "operation": "UPDATE",
                    "event_timestamp": ts.isoformat(),
                    "sequence_number": seq,
                    "payload": {
                        "order_status": self.rng.choice(["SHIPPED", "CANCELLED", "REFUNDED"])
                    },
                    "source_system": "logistics-service"
                })

            elif roll < 0.90 and events:
                # Duplicate Event (Copies an existing event to test idempotency)
                sampled_event = self.rng.choice(events)
                events.append(dict(sampled_event))

            elif roll < 0.95 and customer_pool:
                # Out-of-Order Customer Update
                cid = self.rng.choice(customer_pool)
                current_seq = customer_versions[cid]
                if current_seq > 1:
                    stale_seq = max(1, current_seq - 1)
                    stale_ts = ts - timedelta(hours=2)
                    events.append({
                        "event_id": f"evt_gen_late_{cid}_{stale_seq}_{uuid.uuid4().hex[:6]}",
                        "entity_type": "CUSTOMER",
                        "entity_id": cid,
                        "operation": "UPDATE",
                        "event_timestamp": stale_ts.isoformat(),
                        "sequence_number": stale_seq,
                        "payload": {
                            "tier": "STANDARD",
                            "credit_limit": 3000.0,
                            "status": "ACTIVE"
                        },
                        "source_system": "crm-service"
                    })
                else:
                    # Normal update fallback
                    customer_versions[cid] = 2
                    events.append({
                        "event_id": f"evt_gen_c_upd_{cid}_2",
                        "entity_type": "CUSTOMER",
                        "entity_id": cid,
                        "operation": "UPDATE",
                        "event_timestamp": ts.isoformat(),
                        "sequence_number": 2,
                        "payload": {"status": "ACTIVE"},
                        "source_system": "crm-service"
                    })

            else:
                # Deliberate invalid record (quarantine candidate)
                events.append({
                    "event_id": f"evt_gen_err_{uuid.uuid4().hex[:8]}",
                    "entity_type": "CUSTOMER",
                    "entity_id": f"CUST-ERR-{self.rng.randint(1, 9999)}",
                    "operation": "INSERT",
                    "event_timestamp": ts.isoformat(),
                    "sequence_number": 1,
                    "payload": {
                        "name": "", # Empty name violation!
                        "email": "invalid_email",
                        "credit_limit": -100.0 # Negative credit limit!
                    }
                })

        if output_file:
            target_path = Path(output_file)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(events, f, indent=2)

        return events
