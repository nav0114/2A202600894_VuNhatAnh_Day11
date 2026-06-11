"""
Monitoring and alerting helpers for the defense-in-depth pipeline.
"""
from dataclasses import dataclass


@dataclass
class MonitoringMetrics:
    """Snapshot of pipeline safety metrics used for reporting and alerts."""
    total_requests: int
    input_blocks: int
    rate_limit_hits: int
    output_blocks: int
    output_redactions: int

    @property
    def total_blocks(self) -> int:
        """Count requests blocked by any blocking layer."""
        return self.input_blocks + self.rate_limit_hits + self.output_blocks

    @property
    def block_rate(self) -> float:
        """Percentage of requests blocked by the defense pipeline."""
        if self.total_requests == 0:
            return 0.0
        return self.total_blocks / self.total_requests

    @property
    def rate_limit_hit_rate(self) -> float:
        """Percentage of requests blocked by the rate limiter."""
        if self.total_requests == 0:
            return 0.0
        return self.rate_limit_hits / self.total_requests

    @property
    def redaction_rate(self) -> float:
        """Percentage of responses that required deterministic redaction."""
        if self.total_requests == 0:
            return 0.0
        return self.output_redactions / self.total_requests


class SecurityMonitor:
    """Collect safety metrics and produce alerts for anomalous behavior.

    Why is it needed: Audit logs preserve individual events, while monitoring
    turns many events into operational signals such as high block rate,
    repeated rate-limit hits, or frequent output redaction.
    """

    def __init__(
        self,
        block_rate_threshold: float = 0.5,
        rate_limit_threshold: int = 3,
        redaction_threshold: int = 2,
    ):
        self.block_rate_threshold = block_rate_threshold
        self.rate_limit_threshold = rate_limit_threshold
        self.redaction_threshold = redaction_threshold

    def collect_from_plugins(
        self,
        *,
        rate_plugin,
        input_plugin,
        output_plugin,
        total_requests: int | None = None,
    ) -> MonitoringMetrics:
        """Build a metrics snapshot from the guardrail plugin counters."""
        observed_total = max(
            getattr(input_plugin, "total_count", 0),
            getattr(output_plugin, "total_count", 0),
            total_requests or 0,
        )

        return MonitoringMetrics(
            total_requests=observed_total,
            input_blocks=getattr(input_plugin, "blocked_count", 0),
            rate_limit_hits=getattr(rate_plugin, "blocked_count", 0),
            output_blocks=getattr(output_plugin, "blocked_count", 0),
            output_redactions=getattr(output_plugin, "redacted_count", 0),
        )

    def generate_alerts(self, metrics: MonitoringMetrics) -> list[str]:
        """Return alert messages when metrics cross operational thresholds."""
        alerts = []

        if metrics.block_rate >= self.block_rate_threshold and metrics.total_requests:
            alerts.append(
                f"High block rate: {metrics.block_rate:.0%} "
                f"({metrics.total_blocks}/{metrics.total_requests})"
            )

        if metrics.rate_limit_hits >= self.rate_limit_threshold:
            alerts.append(
                f"Rate-limit spike: {metrics.rate_limit_hits} requests blocked"
            )

        if metrics.output_redactions >= self.redaction_threshold:
            alerts.append(
                f"Output redaction spike: {metrics.output_redactions} responses redacted"
            )

        return alerts

    def print_report(self, metrics: MonitoringMetrics):
        """Print a compact monitoring report for notebook or terminal output."""
        alerts = self.generate_alerts(metrics)

        print("\n" + "=" * 70)
        print("MONITORING REPORT")
        print("=" * 70)
        print(f"  Total requests:     {metrics.total_requests}")
        print(f"  Input blocks:       {metrics.input_blocks}")
        print(f"  Rate-limit hits:    {metrics.rate_limit_hits}")
        print(f"  Output blocks:      {metrics.output_blocks}")
        print(f"  Output redactions:  {metrics.output_redactions}")
        print(f"  Block rate:         {metrics.block_rate:.0%}")
        print(f"  Rate-limit rate:    {metrics.rate_limit_hit_rate:.0%}")
        print(f"  Redaction rate:     {metrics.redaction_rate:.0%}")

        if alerts:
            print("\n  Alerts:")
            for alert in alerts:
                print(f"  - {alert}")
        else:
            print("\n  Alerts: none")
        print("=" * 70)
