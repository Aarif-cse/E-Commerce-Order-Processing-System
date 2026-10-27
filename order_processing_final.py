"""E-Commerce Order Processing System - Final OS PBL prototype.
NIET Greater Noida | Operating Systems (CCSE0303A) | Group 04

Modules demonstrated:
- Process records and state transitions (PCB model)
- FCFS, SJF, non-preemptive Priority, Round Robin, and Priority with ageing
- Binary semaphore protection for shared inventory (critical section)
- Bounded buffer and producer-consumer synchronization
- Counting semaphore for limited packing stations
- Banker's safety algorithm and resource-request decision

All test orders are synthetic; no customer or company data is used.
Run: python order_processing_final.py
"""
from collections import deque
from dataclasses import dataclass, field
import copy
import threading

# ------------------------------ Process / PCB ------------------------------
ALLOWED = {
    "NEW": {"READY", "WAITING"}, "WAITING": {"READY"},
    "READY": {"RUNNING"}, "RUNNING": {"READY", "WAITING", "TERMINATED"},
    "TERMINATED": set(),
}

@dataclass
class Order:
    order_id: str
    product: str
    quantity: int
    arrival: int
    burst: int
    priority: int                 # 1 express, 2 premium, 3 regular
    payment_delay: int = 0
    state: str = "NEW"
    remaining: int = 0
    first_run: int = -1
    completion: int = -1
    history: list = field(default_factory=list)

    def __post_init__(self):
        self.remaining = self.burst
        self.history = [self.state]
        if self.payment_delay:
            self.move_to("WAITING")

    @property
    def ready_time(self):
        return self.arrival + self.payment_delay

    def move_to(self, new_state):
        if new_state not in ALLOWED[self.state]:
            raise ValueError(f"Illegal transition: {self.state} -> {new_state}")
        self.state = new_state
        self.history.append(new_state)


def sample_orders():
    return [
        Order("O1", "Laptop", 1, 0, 8, 2),
        Order("O2", "Phone case", 3, 1, 3, 3),
        Order("O3", "Headphones", 1, 2, 5, 1),
        Order("O4", "Keyboard", 2, 3, 2, 3),
        Order("O5", "Mouse", 1, 4, 4, 2),
        Order("O6", "Monitor", 1, 5, 6, 3, payment_delay=3),
        Order("O7", "USB cable", 5, 6, 1, 1),
        Order("O8", "Webcam", 1, 8, 3, 2),
    ]


def metrics(orders):
    n = len(orders)
    turnaround = [o.completion - o.arrival for o in orders]
    waiting = [turnaround[i] - orders[i].burst for i in range(n)]
    response = [o.first_run - o.arrival for o in orders]
    return tuple(sum(x) / n for x in (waiting, turnaround, response)), max(waiting)


def schedule(algorithm, quantum=3, age_interval=4):
    """Run a CPU scheduler using simulated time and validated state changes."""
    orders = copy.deepcopy(sample_orders())
    pending = sorted(orders, key=lambda o: (o.ready_time, o.order_id))
    ready, gantt = deque(), []
    i, finished, t = 0, 0, 0

    def admit():
        nonlocal i
        while i < len(pending) and pending[i].ready_time <= t:
            o = pending[i]
            o.move_to("READY")
            ready.append(o)
            i += 1

    while finished < len(orders):
        admit()
        if not ready:
            t = pending[i].ready_time
            continue

        if algorithm == "FCFS":
            o = ready.popleft()
        elif algorithm == "SJF":
            o = min(ready, key=lambda x: (x.burst, x.ready_time, x.order_id))
            ready.remove(o)
        elif algorithm in ("Priority", "Priority + ageing"):
            def priority_key(x):
                waited = max(0, t - x.ready_time)
                level = x.priority
                if algorithm == "Priority + ageing":
                    level = max(1, level - waited // age_interval)
                return (level, x.ready_time, x.order_id)
            o = min(ready, key=priority_key)
            ready.remove(o)
        elif algorithm == "Round Robin":
            o = ready.popleft()
        else:
            raise ValueError("Unknown scheduling algorithm")

        o.move_to("RUNNING")
        if o.first_run < 0:
            o.first_run = t
        run_for = min(quantum, o.remaining) if algorithm == "Round Robin" else o.remaining
        start = t
        t += run_for
        o.remaining -= run_for
        gantt.append((o.order_id, start, t))
        admit()
        if o.remaining == 0:
            o.completion = t
            o.move_to("TERMINATED")
            finished += 1
        else:
            o.move_to("READY")
            ready.append(o)

    (avg_wait, avg_tat, avg_response), max_wait = metrics(orders)
    return avg_wait, avg_tat, avg_response, max_wait, gantt

# ------------------------------ Banker's algorithm -------------------------
# Standard 5-process / 3-resource classroom example: resources A, B and C.
AVAILABLE = [3, 3, 2]
ALLOCATION = [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]]
MAXIMUM = [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]]


def safety_check(available, allocation, maximum):
    need = [[maximum[p][r] - allocation[p][r] for r in range(len(available))]
            for p in range(len(allocation))]
    work, finish, sequence = available[:], [False] * len(allocation), []
    while len(sequence) < len(allocation):
        found = False
        for p in range(len(allocation)):
            if not finish[p] and all(need[p][r] <= work[r] for r in range(len(work))):
                work = [work[r] + allocation[p][r] for r in range(len(work))]
                finish[p] = True
                sequence.append(f"P{p}")
                found = True
        if not found:
            return False, sequence
    return True, sequence


def banker_request(pid, request, available, allocation, maximum):
    need = [maximum[pid][r] - allocation[pid][r] for r in range(len(available))]
    if any(request[r] > need[r] for r in range(len(available))):
        return False, "request exceeds declared maximum", []
    if any(request[r] > available[r] for r in range(len(available))):
        return False, "resources are not currently available", []
    for r in range(len(available)):
        available[r] -= request[r]
        allocation[pid][r] += request[r]
    safe, sequence = safety_check(available, allocation, maximum)
    if not safe:
        for r in range(len(available)):
            available[r] += request[r]
            allocation[pid][r] -= request[r]
        return False, "denied: resulting state is unsafe", sequence
    return True, "granted: resulting state is safe", sequence


def banker_demo():
    safe, sequence = safety_check(AVAILABLE[:], copy.deepcopy(ALLOCATION), MAXIMUM)
    print("BANKER'S ALGORITHM")
    print(f"Initial state: {'SAFE' if safe else 'UNSAFE'}; safe sequence: {' -> '.join(sequence)}")
    av1, al1 = AVAILABLE[:], copy.deepcopy(ALLOCATION)
    ok, message, seq = banker_request(1, [1, 0, 2], av1, al1, MAXIMUM)
    print(f"Request P1 [1,0,2]: {message}; sequence: {' -> '.join(seq) if seq else 'none'}")
    av2, al2 = AVAILABLE[:], copy.deepcopy(ALLOCATION)
    ok, message, seq = banker_request(4, [3, 3, 0], av2, al2, MAXIMUM)
    print(f"Request P4 [3,3,0]: {message}")

# ---------------------- Critical section: inventory -------------------------
class Inventory:
    def __init__(self, stock):
        self.stock = stock
        self.mutex = threading.Semaphore(1)  # binary semaphore

    def buy_safe(self, qty):
        self.mutex.acquire()                 # wait(mutex)
        try:
            if self.stock >= qty:
                self.stock -= qty
                return True
            return False
        finally:
            self.mutex.release()             # signal(mutex)


def race_demo(stock=20, buyers=50):
    """Barrier makes every unsafe buyer check the same starting balance."""
    barrier, unsafe_stock, unsafe_results = threading.Barrier(buyers), [stock], []
    unsafe_lock = threading.Lock()
    def unsafe_buyer():
        if unsafe_stock[0] >= 1:
            barrier.wait(timeout=5)
            with unsafe_lock:
                unsafe_stock[0] -= 1
                unsafe_results.append(True)
        else:
            unsafe_results.append(False)
    threads = [threading.Thread(target=unsafe_buyer) for _ in range(buyers)]
    for th in threads: th.start()
    for th in threads: th.join()

    inventory = Inventory(stock)
    safe_results = []
    def safe_buyer(): safe_results.append(inventory.buy_safe(1))
    threads = [threading.Thread(target=safe_buyer) for _ in range(buyers)]
    for th in threads: th.start()
    for th in threads: th.join()
    print("RACE-CONDITION STRESS TEST (50 buyers, 20 units)")
    print(f"Without semaphore: accepted={sum(unsafe_results)}, final stock={unsafe_stock[0]} (oversold)")
    print(f"With binary semaphore: accepted={sum(safe_results)}, final stock={inventory.stock} (correct)")

# -------------------- Bounded buffer / producer-consumer -------------------
class BoundedBuffer:
    def __init__(self, capacity):
        self.items = deque()
        self.capacity = capacity
        self.empty = threading.Semaphore(capacity)
        self.full = threading.Semaphore(0)
        self.mutex = threading.Lock()
        self.max_length = 0

    def put(self, item):
        self.empty.acquire()
        with self.mutex:
            self.items.append(item)
            self.max_length = max(self.max_length, len(self.items))
        self.full.release()

    def get(self):
        self.full.acquire()
        with self.mutex:
            item = self.items.popleft()
        self.empty.release()
        return item


def pipeline_run(order_count=40, stock=40, workers=2, buffer_size=4):
    buffer, inventory = BoundedBuffer(buffer_size), Inventory(stock)
    packing = threading.Semaphore(2)  # two packing stations
    processed, lock = [], threading.Lock()
    def producer():
        for n in range(1, order_count + 1):
            buffer.put((f"O{n:03d}", 1))
        for _ in range(workers): buffer.put(None)
    def consumer():
        while True:
            order = buffer.get()
            if order is None: return
            oid, qty = order
            if inventory.buy_safe(qty):
                packing.acquire()
                try:
                    with lock: processed.append(oid)
                finally:
                    packing.release()
    threads = [threading.Thread(target=consumer) for _ in range(workers)]
    for th in threads: th.start()
    prod = threading.Thread(target=producer)
    prod.start(); prod.join()
    for th in threads: th.join()
    return len(processed), inventory.stock, buffer.max_length


def integrated_pipeline_demo():
    print("THREADED PRODUCER-CONSUMER PIPELINE (40 orders, buffer=4, 2 workers)")
    for run in range(1, 6):
        processed, stock, max_buffer = pipeline_run()
        print(f"Run {run}: processed={processed}/40, final stock={stock}, max buffer={max_buffer}/4")

# ---------------------------------- Main ------------------------------------
def main():
    print("E-COMMERCE ORDER PROCESSING SYSTEM - FINAL TEST RUN")
    print("SCHEDULER COMPARISON (same 8 sample orders)")
    print(f"{'Algorithm':<19}{'Avg wait':>10}{'Avg TAT':>10}{'Avg response':>14}{'Max wait':>11}")
    for algo in ("FCFS", "SJF", "Priority", "Priority + ageing", "Round Robin"):
        wait, tat, response, max_wait, _ = schedule(algo, quantum=3, age_interval=4)
        print(f"{algo:<19}{wait:>10.2f}{tat:>10.2f}{response:>14.2f}{max_wait:>11}")
    print()
    banker_demo(); print()
    race_demo(); print()
    integrated_pipeline_demo()

if __name__ == "__main__":
    main()
