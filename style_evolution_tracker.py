"""
Style Evolution Tracker for Drift Detection and Versioning

This module tracks how a user's writing style evolves over time,
following Letta's continual learning principles:

1. Checkpoint/Versioning: Style profiles can be rolled back, diffed, or branched
2. Memory Self-awareness: Recognize context degradation and restructure
3. Sleep-time Compute: Background processing detects drift and triggers recalculation

Key features:
- Snapshot style profiles at regular intervals
- Detect significant style drift
- Time-weighted profile calculation (recent posts matter more)
- Automatic style recalculation when drift detected
"""

import json
import logging
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class StyleSnapshot:
    """A versioned snapshot of user's style profile."""
    snapshot_id: str
    user_id: str
    created_at: datetime

    # Style profile data
    profile: Dict[str, Any]

    # Metadata
    post_count: int
    trigger: str  # "scheduled", "drift_detected", "manual", "initial"
    notes: Optional[str] = None

    # Comparison data
    drift_from_previous: Optional[float] = None  # Drift score from previous snapshot


@dataclass
class DriftAnalysis:
    """Analysis of style drift between two points in time."""
    overall_drift: float  # 0-1, higher = more drift
    tone_drift: float
    vocabulary_drift: float
    length_drift: float
    structure_drift: float

    significant: bool  # True if drift warrants action
    recommendation: str  # "stable", "recalculate", "alert_user"

    details: Dict[str, Any] = field(default_factory=dict)


class StyleEvolutionTracker:
    """
    Track and manage style evolution over time.

    Enables:
    - Style versioning with rollback capability
    - Drift detection between time periods
    - Time-weighted profile calculation
    - Automatic recalculation triggers
    """

    # Drift thresholds
    DRIFT_THRESHOLD_SIGNIFICANT = 0.3  # Above this = significant drift
    DRIFT_THRESHOLD_CRITICAL = 0.5  # Above this = requires immediate action

    # Time decay settings
    DEFAULT_DECAY_FACTOR = 0.95  # Weight decreases by 5% per day

    def __init__(self, store=None, user_id: str = None):
        """
        Initialize the style evolution tracker.

        Args:
            store: LangGraph store for persistence
            user_id: User ID
        """
        self.store = store
        self.user_id = user_id

    # ═══════════════════════════════════════════════════════════════════════════
    # SNAPSHOT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    def snapshot_style(
        self,
        profile: Dict,
        trigger: str = "manual",
        notes: Optional[str] = None
    ) -> str:
        """
        Save current style profile as a versioned checkpoint.

        Args:
            profile: Current style profile dict
            trigger: What triggered this snapshot
            notes: Optional notes about this snapshot

        Returns:
            Snapshot ID
        """
        if not self.store or not self.user_id:
            logger.warning("Cannot snapshot: no store or user_id")
            return ""

        # Generate snapshot ID
        timestamp = datetime.utcnow()
        snapshot_id = f"style_v{timestamp.strftime('%Y%m%d_%H%M%S')}"

        # Get previous snapshot for drift calculation
        previous = self.get_latest_snapshot()
        drift_from_previous = None
        if previous:
            drift_analysis = self._calculate_drift(previous.profile, profile)
            drift_from_previous = drift_analysis.overall_drift

        # Create snapshot
        snapshot = StyleSnapshot(
            snapshot_id=snapshot_id,
            user_id=self.user_id,
            created_at=timestamp,
            profile=profile,
            post_count=profile.get("post_count", 0),
            trigger=trigger,
            notes=notes,
            drift_from_previous=drift_from_previous
        )

        # Save to store
        try:
            namespace = (self.user_id, "style_evolution")
            self.store.put(namespace, snapshot_id, {
                "snapshot_id": snapshot_id,
                "user_id": self.user_id,
                "created_at": timestamp.isoformat(),
                "profile": profile,
                "post_count": snapshot.post_count,
                "trigger": trigger,
                "notes": notes,
                "drift_from_previous": drift_from_previous
            })
            logger.info(f"Created style snapshot {snapshot_id} for user {self.user_id}")
            return snapshot_id
        except Exception as e:
            logger.error(f"Failed to save style snapshot: {e}")
            return ""

    def get_snapshot(self, snapshot_id: str) -> Optional[StyleSnapshot]:
        """Get a specific style snapshot by ID."""
        if not self.store or not self.user_id:
            return None

        try:
            namespace = (self.user_id, "style_evolution")
            result = self.store.get(namespace, snapshot_id)
            if result and result.value:
                data = result.value
                return StyleSnapshot(
                    snapshot_id=data["snapshot_id"],
                    user_id=data["user_id"],
                    created_at=datetime.fromisoformat(data["created_at"]),
                    profile=data["profile"],
                    post_count=data.get("post_count", 0),
                    trigger=data.get("trigger", "unknown"),
                    notes=data.get("notes"),
                    drift_from_previous=data.get("drift_from_previous")
                )
        except Exception as e:
            logger.error(f"Failed to get snapshot {snapshot_id}: {e}")

        return None

    def get_latest_snapshot(self) -> Optional[StyleSnapshot]:
        """Get the most recent style snapshot."""
        snapshots = self.list_snapshots(limit=1)
        return snapshots[0] if snapshots else None

    def list_snapshots(self, limit: int = 10) -> List[StyleSnapshot]:
        """List recent style snapshots."""
        if not self.store or not self.user_id:
            return []

        try:
            namespace = (self.user_id, "style_evolution")
            results = self.store.search(namespace, query="style_v")

            snapshots = []
            for r in results:
                data = r.value
                snapshots.append(StyleSnapshot(
                    snapshot_id=data["snapshot_id"],
                    user_id=data["user_id"],
                    created_at=datetime.fromisoformat(data["created_at"]),
                    profile=data["profile"],
                    post_count=data.get("post_count", 0),
                    trigger=data.get("trigger", "unknown"),
                    notes=data.get("notes"),
                    drift_from_previous=data.get("drift_from_previous")
                ))

            # Sort by date descending
            snapshots.sort(key=lambda s: s.created_at, reverse=True)
            return snapshots[:limit]
        except Exception as e:
            logger.error(f"Failed to list snapshots: {e}")
            return []

    def rollback_to_snapshot(self, snapshot_id: str) -> Optional[Dict]:
        """
        Rollback to a previous style snapshot.

        Args:
            snapshot_id: ID of snapshot to restore

        Returns:
            Restored profile dict, or None if failed
        """
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            logger.error(f"Snapshot {snapshot_id} not found")
            return None

        # Create a new snapshot with the restored profile
        self.snapshot_style(
            profile=snapshot.profile,
            trigger="rollback",
            notes=f"Rolled back from {snapshot_id}"
        )

        logger.info(f"Rolled back to snapshot {snapshot_id}")
        return snapshot.profile

    # ═══════════════════════════════════════════════════════════════════════════
    # DRIFT DETECTION
    # ═══════════════════════════════════════════════════════════════════════════

    def detect_drift(
        self,
        current_profile: Dict,
        window_days: int = 30
    ) -> DriftAnalysis:
        """
        Detect style drift compared to historical profile.

        Args:
            current_profile: Current style profile
            window_days: Compare against profile from this many days ago

        Returns:
            DriftAnalysis with metrics and recommendation
        """
        # Get historical snapshot
        cutoff = datetime.utcnow() - timedelta(days=window_days)
        historical = self._get_snapshot_before(cutoff)

        if not historical:
            # No historical data - can't detect drift
            return DriftAnalysis(
                overall_drift=0.0,
                tone_drift=0.0,
                vocabulary_drift=0.0,
                length_drift=0.0,
                structure_drift=0.0,
                significant=False,
                recommendation="stable",
                details={"reason": "No historical data available"}
            )

        return self._calculate_drift(historical.profile, current_profile)

    def _calculate_drift(
        self,
        old_profile: Dict,
        new_profile: Dict
    ) -> DriftAnalysis:
        """Calculate drift between two profiles."""
        drift_scores = {}

        # 1. Tone drift
        old_tone = old_profile.get("tone", "neutral")
        new_tone = new_profile.get("tone", "neutral")
        old_tone_scores = old_profile.get("tone_scores", {})
        new_tone_scores = new_profile.get("tone_scores", {})

        if old_tone_scores and new_tone_scores:
            # Calculate cosine distance between tone vectors
            tone_drift = self._dict_distance(old_tone_scores, new_tone_scores)
        elif old_tone != new_tone:
            tone_drift = 0.5
        else:
            tone_drift = 0.0

        drift_scores["tone"] = tone_drift

        # 2. Vocabulary drift
        old_vocab = set(old_profile.get("domain_vocabulary", []))
        new_vocab = set(new_profile.get("domain_vocabulary", []))

        if old_vocab or new_vocab:
            vocab_overlap = len(old_vocab & new_vocab)
            vocab_union = len(old_vocab | new_vocab)
            vocab_drift = 1.0 - (vocab_overlap / vocab_union) if vocab_union > 0 else 0.0
        else:
            vocab_drift = 0.0

        drift_scores["vocabulary"] = vocab_drift

        # 3. Length drift
        old_post_len = old_profile.get("avg_post_length", 100)
        new_post_len = new_profile.get("avg_post_length", 100)
        old_comment_len = old_profile.get("avg_comment_length", 50)
        new_comment_len = new_profile.get("avg_comment_length", 50)

        post_len_ratio = abs(new_post_len - old_post_len) / max(old_post_len, 1)
        comment_len_ratio = abs(new_comment_len - old_comment_len) / max(old_comment_len, 1)
        length_drift = min(1.0, (post_len_ratio + comment_len_ratio) / 2)

        drift_scores["length"] = length_drift

        # 4. Structure drift
        old_sent_len = old_profile.get("avg_sentence_length", 15)
        new_sent_len = new_profile.get("avg_sentence_length", 15)
        sent_drift = abs(new_sent_len - old_sent_len) / max(old_sent_len, 1)

        old_punct = old_profile.get("punctuation_patterns", {})
        new_punct = new_profile.get("punctuation_patterns", {})
        punct_drift = self._dict_distance(old_punct, new_punct)

        structure_drift = min(1.0, (sent_drift + punct_drift) / 2)
        drift_scores["structure"] = structure_drift

        # Calculate overall drift (weighted average)
        overall = (
            tone_drift * 0.3 +
            vocab_drift * 0.3 +
            length_drift * 0.2 +
            structure_drift * 0.2
        )

        # Determine significance and recommendation
        if overall >= self.DRIFT_THRESHOLD_CRITICAL:
            significant = True
            recommendation = "alert_user"
        elif overall >= self.DRIFT_THRESHOLD_SIGNIFICANT:
            significant = True
            recommendation = "recalculate"
        else:
            significant = False
            recommendation = "stable"

        return DriftAnalysis(
            overall_drift=round(overall, 3),
            tone_drift=round(tone_drift, 3),
            vocabulary_drift=round(vocab_drift, 3),
            length_drift=round(length_drift, 3),
            structure_drift=round(structure_drift, 3),
            significant=significant,
            recommendation=recommendation,
            details={
                "old_tone": old_tone,
                "new_tone": new_tone,
                "old_post_length": old_post_len,
                "new_post_length": new_post_len
            }
        )

    def _dict_distance(self, dict1: Dict, dict2: Dict) -> float:
        """Calculate normalized distance between two dicts."""
        if not dict1 and not dict2:
            return 0.0
        if not dict1 or not dict2:
            return 1.0

        all_keys = set(dict1.keys()) | set(dict2.keys())
        if not all_keys:
            return 0.0

        total_diff = 0.0
        for key in all_keys:
            v1 = dict1.get(key, 0)
            v2 = dict2.get(key, 0)
            total_diff += abs(v1 - v2)

        # Normalize
        max_diff = len(all_keys) * 1.0  # Assuming values are 0-1
        return min(1.0, total_diff / max_diff) if max_diff > 0 else 0.0

    def _get_snapshot_before(self, cutoff: datetime) -> Optional[StyleSnapshot]:
        """Get the most recent snapshot before the cutoff date."""
        snapshots = self.list_snapshots(limit=50)

        for snapshot in snapshots:
            if snapshot.created_at < cutoff:
                return snapshot

        return None

    # ═══════════════════════════════════════════════════════════════════════════
    # TIME-WEIGHTED PROFILE
    # ═══════════════════════════════════════════════════════════════════════════

    def get_time_weighted_profile(
        self,
        posts: List[Dict],
        decay_factor: float = None
    ) -> Dict:
        """
        Calculate style profile with time-weighted posts.

        Recent posts influence style more than old posts.
        Weight = decay_factor ^ days_old

        Args:
            posts: List of posts with 'content', 'timestamp', etc.
            decay_factor: How fast weight decays (default 0.95)

        Returns:
            Weighted style profile
        """
        if not posts:
            return {}

        if decay_factor is None:
            decay_factor = self.DEFAULT_DECAY_FACTOR

        now = datetime.utcnow()
        weighted_lengths = []
        weighted_words = Counter()
        total_weight = 0.0

        for post in posts:
            # Calculate weight based on age
            timestamp = post.get("timestamp")
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            elif not timestamp:
                timestamp = now

            days_old = (now - timestamp).days if isinstance(timestamp, datetime) else 0
            weight = decay_factor ** days_old

            # Weighted content analysis
            content = post.get("content", "")
            weighted_lengths.append((len(content), weight))

            # Weighted word frequency
            words = content.lower().split()
            for word in words:
                if len(word) > 3:  # Skip short words
                    weighted_words[word] += weight

            total_weight += weight

        # Calculate weighted averages
        if total_weight > 0:
            avg_length = sum(l * w for l, w in weighted_lengths) / total_weight
        else:
            avg_length = 100

        # Get top weighted vocabulary
        top_vocab = [word for word, _ in weighted_words.most_common(50)]

        return {
            "avg_post_length": int(avg_length),
            "domain_vocabulary": top_vocab,
            "total_weight": total_weight,
            "post_count": len(posts),
            "calculation_method": "time_weighted",
            "decay_factor": decay_factor
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # COMPARISON AND DIFF
    # ═══════════════════════════════════════════════════════════════════════════

    def diff_snapshots(
        self,
        snapshot_id_1: str,
        snapshot_id_2: str
    ) -> Dict:
        """
        Compare two snapshots and return differences.

        Args:
            snapshot_id_1: First snapshot ID (older)
            snapshot_id_2: Second snapshot ID (newer)

        Returns:
            Dict with differences
        """
        snapshot1 = self.get_snapshot(snapshot_id_1)
        snapshot2 = self.get_snapshot(snapshot_id_2)

        if not snapshot1 or not snapshot2:
            return {"error": "Snapshot not found"}

        drift = self._calculate_drift(snapshot1.profile, snapshot2.profile)

        return {
            "from_snapshot": snapshot_id_1,
            "to_snapshot": snapshot_id_2,
            "time_between": str(snapshot2.created_at - snapshot1.created_at),
            "drift_analysis": {
                "overall": drift.overall_drift,
                "tone": drift.tone_drift,
                "vocabulary": drift.vocabulary_drift,
                "length": drift.length_drift,
                "structure": drift.structure_drift,
                "significant": drift.significant
            },
            "profile_changes": {
                "tone": {
                    "from": snapshot1.profile.get("tone"),
                    "to": snapshot2.profile.get("tone")
                },
                "avg_post_length": {
                    "from": snapshot1.profile.get("avg_post_length"),
                    "to": snapshot2.profile.get("avg_post_length")
                },
                "avg_comment_length": {
                    "from": snapshot1.profile.get("avg_comment_length"),
                    "to": snapshot2.profile.get("avg_comment_length")
                }
            }
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # SCHEDULED TASKS
    # ═══════════════════════════════════════════════════════════════════════════

    async def check_and_snapshot_if_needed(
        self,
        current_profile: Dict,
        force: bool = False
    ) -> Optional[str]:
        """
        Check if a new snapshot is needed and create one if so.

        Called periodically (e.g., daily) as part of sleep-time compute.

        Args:
            current_profile: Current style profile
            force: Force snapshot regardless of conditions

        Returns:
            Snapshot ID if created, None otherwise
        """
        if force:
            return self.snapshot_style(current_profile, trigger="scheduled")

        # Check if we should snapshot
        latest = self.get_latest_snapshot()

        if not latest:
            # No snapshots yet - create initial
            return self.snapshot_style(current_profile, trigger="initial")

        # Check time since last snapshot (at least 7 days)
        days_since_last = (datetime.utcnow() - latest.created_at).days
        if days_since_last < 7:
            return None

        # Check for significant drift
        drift = self._calculate_drift(latest.profile, current_profile)

        if drift.significant:
            return self.snapshot_style(
                current_profile,
                trigger="drift_detected",
                notes=f"Drift score: {drift.overall_drift:.2f}"
            )

        # Regular scheduled snapshot (every 30 days)
        if days_since_last >= 30:
            return self.snapshot_style(current_profile, trigger="scheduled")

        return None

    def get_evolution_summary(self) -> Dict:
        """
        Get summary of style evolution over time.

        Returns:
            Summary dict with evolution metrics
        """
        snapshots = self.list_snapshots(limit=20)

        if len(snapshots) < 2:
            return {
                "snapshots_count": len(snapshots),
                "evolution_detected": False,
                "message": "Not enough snapshots to analyze evolution"
            }

        # Calculate evolution metrics
        total_drift = 0.0
        drift_history = []

        for i in range(len(snapshots) - 1):
            newer = snapshots[i]
            older = snapshots[i + 1]
            drift = self._calculate_drift(older.profile, newer.profile)
            total_drift += drift.overall_drift
            drift_history.append({
                "from": older.snapshot_id,
                "to": newer.snapshot_id,
                "drift": drift.overall_drift,
                "date": newer.created_at.isoformat()
            })

        avg_drift = total_drift / (len(snapshots) - 1)

        return {
            "snapshots_count": len(snapshots),
            "oldest_snapshot": snapshots[-1].created_at.isoformat(),
            "newest_snapshot": snapshots[0].created_at.isoformat(),
            "average_drift": round(avg_drift, 3),
            "evolution_detected": avg_drift > 0.1,
            "drift_history": drift_history[:5],  # Last 5 drifts
            "current_trigger_status": snapshots[0].trigger
        }


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def create_evolution_tracker(store, user_id: str) -> StyleEvolutionTracker:
    """
    Create a StyleEvolutionTracker instance.

    Args:
        store: LangGraph store
        user_id: User ID

    Returns:
        StyleEvolutionTracker instance
    """
    return StyleEvolutionTracker(store=store, user_id=user_id)
