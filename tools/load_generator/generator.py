"""
Load Generator for Real-Time Analytics Platform

Simulates multi-tenant metric ingestion with realistic patterns.
Tests the full pipeline: FastAPI -> Kafka -> Worker -> TimescaleDB

Usage:
    python generator.py --rate 10 --duration 300
    python generator.py --rate 100 --tenants acme,globex,initech
"""

import argparse
import asyncio
import math
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import httpx
from rich.console import Console
from rich.live import Live
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Config
API_URL = "http://localhost:8000/api/v1"
TENANTS = ["acme", "globex", "initech"]
METRIC_TYPES = [
    "cpu_usage",
    "memory_usage",
    "request_latency",
    "request_rate",
    "error_rate",
]


@dataclass
class GeneratorStats:
    """Track generator performance metrics."""

    total_sent: int = 0
    total_success: int = 0
    total_failed: int = 0
    total_duration: float = 0.0

    def success_rate(
        self,
    ) -> float:
        """
        Calculate the success rate percentage
        """
        if self.total_sent == 0:
            return 0.0
        return (self.total_success / self.total_sent) * 100

    def avg_latency_ms(
        self,
    ) -> float:
        """
        Calculate avg request latency
        """
        if self.total_sent == 0:
            return 0.0
        return (self.total_duration / self.total_sent) * 1000


class MetricGenerator:
    """Generates realistic metric values based on patterns."""

    def __init__(self):
        self.start_time = time.time()
        # Track state for stateful metrics (memory grows over time, etc.)
        self.memory_base = {tenant: random.uniform(40, 60) for tenant in TENANTS}

    def generate_cpu_usage(self, tenant: str) -> float:
        """
        CPU usage pattern:
        - Base: 20-40%
        - Occasional spikes to 80-95%
        - Small random fluctuations
        """
        base = random.uniform(20, 40)
        # 5% chance of spike
        if random.random() < 0.05:
            return random.uniform(80, 95)
        # Small noise
        return base + random.uniform(-5, 5)

    def generate_memory_usage(self, tenant: str) -> float:
        """
        Memory usage pattern:
        - Gradual growth over time (simulating memory leak)
        - Resets occasionally (simulating restart)
        """
        elapsed_minutes = (time.time() - self.start_time) / 60

        # Reset every 30 minutes (simulate restart)
        if elapsed_minutes > 0 and int(elapsed_minutes) % 30 == 0:
            self.memory_base[tenant] = random.uniform(40, 60)

        # Gradual growth: +0.1% per minute
        growth = elapsed_minutes * 0.1
        current = self.memory_base[tenant] + growth

        # Cap at 90%
        return min(current, 90.0) + random.uniform(-2, 2)

    def generate_request_latency(self, tenant: str) -> float:
        """
        Latency pattern (long-tail distribution):
        - P50: ~50ms
        - P95: ~200ms
        - P99: ~500ms
        - Occasional outliers: 1000ms+
        """
        # 95% of requests: 20-100ms
        if random.random() < 0.95:
            return random.uniform(20, 100)
        # 4% of requests: 100-500ms
        elif random.random() < 0.99:
            return random.uniform(100, 500)
        # 1% of requests: 500-2000ms (outliers)
        else:
            return random.uniform(500, 2000)

    def generate_request_rate(self, tenant: str) -> float:
        """
        Request rate pattern (follows daily traffic cycle):
        - Uses sine wave to simulate day/night traffic
        - Peak during "business hours"
        """
        elapsed_hours = (time.time() - self.start_time) / 3600
        # Sine wave: oscillates between 100-500 req/sec
        base = 300 + 200 * math.sin(elapsed_hours * 3.14159 / 12)
        return base + random.uniform(-20, 20)

    def generate_error_rate(self, tenant: str) -> float:
        """
        Error rate pattern:
        - Usually low: 0.1-1%
        - Occasional spikes: 5-10% (simulating outages)
        """
        # 95% of time: low error rate
        if random.random() < 0.95:
            return random.uniform(0.1, 1.0)
        # 5% of time: elevated errors
        else:
            return random.uniform(5.0, 10.0)

    def generate_metric(self, tenant: str, metric_type: str) -> dict:
        """Generate a single metric payload."""
        generators = {
            "cpu_usage": self.generate_cpu_usage,
            "memory_usage": self.generate_memory_usage,
            "request_latency": self.generate_request_latency,
            "request_rate": self.generate_request_rate,
            "error_rate": self.generate_error_rate,
        }

        value = generators[metric_type](tenant)

        return {
            "name": metric_type,
            "value": round(value, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant,
            "labels": {
                "host": f"{tenant}-host-{random.randint(1, 5)}",
                "region": random.choice(["us-east-1", "us-west-2", "eu-west-1"]),
                "environment": "production",
            },
        }


class LoadGenerator:
    """
    Orchestrates load generation with rate limiting and stats tracking.

    Features:
    - Async HTTP requests with connection pooling
    - Configurable rate limiting (requests per second)
    - Real-time stats display
    - Graceful shutdown on Ctrl+C
    """

    def __init__(
        self, api_url: str, tenants: List[str], rate: int, duration: int = None
    ):
        self.api_url = api_url
        self.tenants = tenants
        self.rate = rate  # requests per second
        self.duration = duration  # total seconds to run (None = infinite)

        self.metric_gen = MetricGenerator()
        self.stats = GeneratorStats()
        self.console = Console()

        # HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

        # Running state
        self.running = False
        self.start_time = None

    async def send_metric(self, metric: dict) -> bool:
        """
        Send a single metric to the API endpoint.

        Returns:
            True if successful, False otherwise
        """
        request_start = time.time()

        try:
            response = await self.client.post(
                f"{self.api_url}/metrics",
                json=metric,
                headers={"Content-Type": "application/json"},
            )

            request_duration = time.time() - request_start
            self.stats.total_duration += request_duration

            if response.status_code == 202:
                self.stats.total_success += 1
                return True
            else:
                self.stats.total_failed += 1
                # Log errors occasionally (not every failure, too noisy)
                if self.stats.total_failed % 100 == 1:
                    self.console.print(
                        f"[red]HTTP {response.status_code}:[/red] {response.text[:100]}"
                    )
                return False

        except Exception as e:
            self.stats.total_failed += 1
            # Log errors occasionally
            if self.stats.total_failed % 100 == 1:
                self.console.print(f"[red]Error:[/red] {str(e)[:100]}")
            return False

        finally:
            self.stats.total_sent += 1

    def create_stats_table(self) -> Table:
        """Create a rich Table with current statistics."""
        table = Table(
            title="Load Generator Stats", show_header=True, header_style="bold magenta"
        )

        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", style="green", width=30)

        # Runtime
        if self.start_time:
            elapsed = time.time() - self.start_time
            table.add_row("Runtime", f"{elapsed:.1f}s")

        # Throughput
        table.add_row("Target Rate", f"{self.rate} req/s")
        if self.start_time:
            actual_rate = self.stats.total_sent / elapsed if elapsed > 0 else 0
            table.add_row("Actual Rate", f"{actual_rate:.1f} req/s")

        # Requests
        table.add_row("Total Sent", str(self.stats.total_sent))
        table.add_row(
            "Successful",
            f"{self.stats.total_success} ({self.stats.success_rate():.1f}%)",
        )
        table.add_row("Failed", str(self.stats.total_failed))

        # Latency
        table.add_row("Avg Latency", f"{self.stats.avg_latency_ms():.2f}ms")

        return table

    async def generate_continuously(self):
        """
        Main generation loop.

        Generates metrics at the configured rate until stopped or duration expires.
        Uses asyncio.sleep to control rate limiting.
        """
        self.running = True
        self.start_time = time.time()

        # Calculate delay between requests to achieve target rate
        delay = 1.0 / self.rate

        try:
            while self.running:
                # Check duration limit
                if self.duration and (time.time() - self.start_time) >= self.duration:
                    self.console.print(
                        "\n[yellow]Duration limit reached. Stopping...[/yellow]"
                    )
                    break

                # Generate and send one metric
                tenant = random.choice(self.tenants)
                metric_type = random.choice(METRIC_TYPES)
                metric = self.metric_gen.generate_metric(tenant, metric_type)

                # Send asynchronously (don't await - fire and forget for max throughput)
                asyncio.create_task(self.send_metric(metric))

                # Rate limiting: sleep to maintain target rate
                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            self.console.print("\n[yellow]Cancelled by user[/yellow]")
        finally:
            self.running = False

    async def run(self):
        """
        Start the load generator with live stats display.

        Runs until:
        - Duration expires (if set)
        - User presses Ctrl+C
        - Error occurs
        """
        self.console.print(f"[bold green]Starting Load Generator[/bold green]")
        self.console.print(f"Target: {self.api_url}")
        self.console.print(f"Rate: {self.rate} req/s")
        self.console.print(f"Tenants: {', '.join(self.tenants)}")
        self.console.print(f"Metrics: {', '.join(METRIC_TYPES)}")
        if self.duration:
            self.console.print(f"Duration: {self.duration}s")
        self.console.print("\n[dim]Press Ctrl+C to stop[/dim]\n")

        # Start generation task
        generation_task = asyncio.create_task(self.generate_continuously())

        # Live stats display (updates every second)
        try:
            with Live(
                self.create_stats_table(), refresh_per_second=1, console=self.console
            ) as live:
                while self.running:
                    await asyncio.sleep(1)
                    live.update(self.create_stats_table())

                # Wait for generation to finish
                await generation_task

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Stopping...[/yellow]")
            self.running = False
            generation_task.cancel()
            try:
                await generation_task
            except asyncio.CancelledError:
                pass

        finally:
            await self.client.aclose()

            # Final stats
            self.console.print("\n[bold]Final Statistics:[/bold]")
            self.console.print(self.create_stats_table())


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Load Generator for Real-Time Analytics Platform"
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=10,
        help="Target rate in requests per second (default: 10)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Duration in seconds (default: run until Ctrl+C)",
    )
    parser.add_argument(
        "--tenants",
        type=str,
        default="acme,globex,initech",
        help="Comma-separated list of tenant IDs (default: acme,globex,initech)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8000/api/v1",
        help="API base URL (default: http://localhost:8000/api/v1)",
    )

    args = parser.parse_args()

    tenants = [t.strip() for t in args.tenants.split(",")]

    generator = LoadGenerator(
        api_url=args.api_url, tenants=tenants, rate=args.rate, duration=args.duration
    )

    await generator.run()


if __name__ == "__main__":
    asyncio.run(main())
