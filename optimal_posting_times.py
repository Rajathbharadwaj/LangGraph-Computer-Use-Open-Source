"""
Optimal Posting Times Analytics Module

Combines industry best practices with your historical engagement data
to determine the best times to schedule X posts.
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from database import ScheduledPost, UserPost, XAccount
import logging

logger = logging.getLogger(__name__)


class OptimalPostingTimesAnalyzer:
    """Analyzes engagement data to determine optimal posting times"""

    # Industry best practices from Buffer analysis (2025 data)
    INDUSTRY_BEST_TIMES = {
        # Monday through Friday: morning slots (7-10 AM)
        0: [8, 9, 10],      # Monday
        1: [8, 9, 10],      # Tuesday (best day overall)
        2: [9, 8, 10],      # Wednesday (9 AM is peak)
        3: [9, 8, 10],      # Thursday
        4: [8, 9, 7],       # Friday
        5: [8, 7, 9],       # Saturday
        6: [8, 7, 9],       # Sunday (lowest engagement day)
    }

    # Secondary times (afternoon slots)
    INDUSTRY_SECONDARY_TIMES = {
        0: [12, 13, 14],    # Monday afternoon
        1: [12, 13, 14],    # Tuesday afternoon
        2: [12, 13, 14],    # Wednesday afternoon
        3: [12, 13, 14],    # Thursday afternoon
        4: [12, 13],        # Friday afternoon (less engagement)
        5: [11, 12],        # Saturday afternoon
        6: [11, 12],        # Sunday afternoon
    }

    # Evening slots (5-6 PM for working professionals)
    INDUSTRY_EVENING_TIMES = {
        0: [17, 18],
        1: [17, 18],
        2: [17, 18],
        3: [17, 18],
        4: [17],
        5: [17],
        6: [17],
    }

    def __init__(self, db: Session):
        self.db = db

    def calculate_engagement_score(self, likes: int, retweets: int, replies: int) -> float:
        """
        Calculate weighted engagement score
        Replies are weighted highest (3x), retweets medium (2x), likes baseline (1x)
        """
        return (likes or 0) + (retweets or 0) * 2 + (replies or 0) * 3

    def get_historical_best_times(
        self,
        user_id: str,
        min_posts_threshold: int = 2
    ) -> Dict[int, List[Tuple[int, float]]]:
        """
        Analyze user's historical posts to find their best performing hours

        Args:
            user_id: The user's ID
            min_posts_threshold: Minimum number of posts in an hour to consider it valid

        Returns:
            Dict mapping day_of_week (0-6) to list of (hour, avg_engagement_score) tuples
        """
        # Get user's X accounts
        x_accounts = self.db.query(XAccount).filter(XAccount.user_id == user_id).all()
        if not x_accounts:
            logger.warning(f"No X accounts found for user {user_id}")
            return {}

        x_account_ids = [acc.id for acc in x_accounts]

        # Query engagement by day of week and hour
        results = self.db.query(
            extract('dow', UserPost.posted_at).label('day_of_week'),
            extract('hour', UserPost.posted_at).label('hour'),
            func.count(UserPost.id).label('post_count'),
            func.avg(
                (func.coalesce(UserPost.likes, 0) +
                 func.coalesce(UserPost.retweets, 0) * 2 +
                 func.coalesce(UserPost.replies, 0) * 3)
            ).label('avg_engagement')
        ).filter(
            UserPost.x_account_id.in_(x_account_ids),
            UserPost.posted_at.isnot(None)
        ).group_by(
            extract('dow', UserPost.posted_at),
            extract('hour', UserPost.posted_at)
        ).having(
            func.count(UserPost.id) >= min_posts_threshold
        ).all()

        # Organize by day of week
        best_times_by_day = {}
        for row in results:
            day_of_week = int(row.day_of_week)
            hour = int(row.hour)
            avg_engagement = float(row.avg_engagement)

            if day_of_week not in best_times_by_day:
                best_times_by_day[day_of_week] = []

            best_times_by_day[day_of_week].append((hour, avg_engagement))

        # Sort each day's hours by engagement score (descending)
        for day in best_times_by_day:
            best_times_by_day[day] = sorted(
                best_times_by_day[day],
                key=lambda x: x[1],
                reverse=True
            )

        return best_times_by_day

    def get_optimal_times_for_day(
        self,
        date: datetime,
        user_id: str,
        num_slots: int = 3,
        use_historical: bool = True
    ) -> List[datetime]:
        """
        Get optimal posting times for a specific date

        Args:
            date: The date to schedule for
            user_id: User's ID for historical analysis
            num_slots: Number of time slots to return
            use_historical: Whether to blend with historical data

        Returns:
            List of datetime objects with optimal posting times
        """
        day_of_week = date.weekday()

        # Get industry best times for this day
        primary_hours = self.INDUSTRY_BEST_TIMES[day_of_week]
        secondary_hours = self.INDUSTRY_SECONDARY_TIMES[day_of_week]
        evening_hours = self.INDUSTRY_EVENING_TIMES[day_of_week]

        # Combine all industry recommended hours
        industry_hours = primary_hours + secondary_hours + evening_hours

        # If we have historical data, blend it with industry data
        if use_historical:
            historical_data = self.get_historical_best_times(user_id)

            if day_of_week in historical_data:
                # Get top historical hours (that have good engagement)
                historical_hours = [
                    hour for hour, score in historical_data[day_of_week][:num_slots * 2]
                    if score > 5  # Only use hours with meaningful engagement
                ]

                # Blend: prioritize hours that appear in both lists
                blended_hours = []

                # First, add hours that appear in both (proven winners)
                for hour in industry_hours:
                    if hour in historical_hours and hour not in blended_hours:
                        blended_hours.append(hour)

                # Then add remaining industry hours
                for hour in industry_hours:
                    if hour not in blended_hours:
                        blended_hours.append(hour)

                # Finally, add high-performing historical hours
                for hour in historical_hours:
                    if hour not in blended_hours:
                        blended_hours.append(hour)

                selected_hours = blended_hours[:num_slots]
            else:
                # No historical data for this day, use industry best practices
                selected_hours = industry_hours[:num_slots]
        else:
            selected_hours = industry_hours[:num_slots]

        # Convert hours to datetime objects
        optimal_times = []
        for hour in selected_hours:
            posting_time = datetime(
                date.year,
                date.month,
                date.day,
                hour,
                0,
                0
            )
            optimal_times.append(posting_time)

        return optimal_times

    def get_next_optimal_time(
        self,
        user_id: str,
        start_from: Optional[datetime] = None,
        avoid_times: Optional[List[datetime]] = None
    ) -> datetime:
        """
        Get the next optimal posting time

        Args:
            user_id: User's ID
            start_from: Start searching from this datetime (default: now)
            avoid_times: List of times to avoid (already scheduled posts)

        Returns:
            Next optimal posting datetime
        """
        if start_from is None:
            start_from = datetime.now()

        if avoid_times is None:
            avoid_times = []

        # Look ahead up to 7 days
        for days_ahead in range(7):
            check_date = start_from + timedelta(days=days_ahead)

            # Get optimal times for this day
            optimal_times = self.get_optimal_times_for_day(
                check_date,
                user_id,
                num_slots=5  # Check more slots to find available ones
            )

            # Find first available time that's:
            # 1. In the future
            # 2. Not in avoid_times list
            for optimal_time in optimal_times:
                if optimal_time <= start_from:
                    continue

                # Check if this time conflicts with already scheduled posts
                # (within 30 minutes)
                is_available = True
                for avoid_time in avoid_times:
                    time_diff = abs((optimal_time - avoid_time).total_seconds())
                    if time_diff < 1800:  # 30 minutes
                        is_available = False
                        break

                if is_available:
                    return optimal_time

        # Fallback: if no optimal time found, return next industry best time
        tomorrow = start_from + timedelta(days=1)
        day_of_week = tomorrow.weekday()
        best_hour = self.INDUSTRY_BEST_TIMES[day_of_week][0]

        return datetime(
            tomorrow.year,
            tomorrow.month,
            tomorrow.day,
            best_hour,
            0,
            0
        )

    def get_weekly_optimal_schedule(
        self,
        user_id: str,
        num_posts_per_day: int = 3,
        start_date: Optional[datetime] = None
    ) -> List[datetime]:
        """
        Generate a full week's optimal posting schedule

        Args:
            user_id: User's ID
            num_posts_per_day: Number of posts to schedule per day
            start_date: Start date (default: tomorrow)

        Returns:
            List of optimal posting times for the week
        """
        if start_date is None:
            start_date = datetime.now() + timedelta(days=1)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        weekly_schedule = []

        for days_ahead in range(7):
            date = start_date + timedelta(days=days_ahead)
            day_times = self.get_optimal_times_for_day(
                date,
                user_id,
                num_slots=num_posts_per_day
            )
            weekly_schedule.extend(day_times)

        return sorted(weekly_schedule)

    def get_posting_rationale(
        self,
        posting_time: datetime,
        user_id: str
    ) -> str:
        """
        Get human-readable explanation of why this time was chosen

        Args:
            posting_time: The scheduled posting time
            user_id: User's ID

        Returns:
            Explanation string
        """
        day_of_week = posting_time.weekday()
        hour = posting_time.hour

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_name = day_names[day_of_week]

        # Check if it's an industry best time
        is_primary = hour in self.INDUSTRY_BEST_TIMES[day_of_week]
        is_secondary = hour in self.INDUSTRY_SECONDARY_TIMES[day_of_week]
        is_evening = hour in self.INDUSTRY_EVENING_TIMES[day_of_week]

        # Check historical performance
        historical_data = self.get_historical_best_times(user_id)
        historical_performance = None

        if day_of_week in historical_data:
            for hist_hour, score in historical_data[day_of_week]:
                if hist_hour == hour:
                    historical_performance = score
                    break

        # Build rationale
        reasons = []

        if is_primary:
            if day_of_week == 2 and hour == 9:
                reasons.append("Peak engagement time (Wednesday 9 AM is the #1 best time across all of X)")
            elif day_of_week == 1:
                reasons.append("Tuesday morning - highest overall engagement day")
            else:
                reasons.append("Industry peak time - high engagement expected")
        elif is_secondary:
            reasons.append("Strong afternoon engagement window")
        elif is_evening:
            reasons.append("Evening commute time - working professionals active")

        if historical_performance and historical_performance > 10:
            reasons.append(f"Your posts at this time historically perform well (avg engagement: {historical_performance:.1f})")
        elif historical_performance:
            reasons.append(f"Based on your posting history")

        if not reasons:
            reasons.append("Recommended posting time based on industry data")

        return f"{day_name} {hour}:00 - " + "; ".join(reasons)


# Convenience function for quick usage
def get_next_optimal_posting_time(
    db: Session,
    user_id: str,
    start_from: Optional[datetime] = None
) -> Tuple[datetime, str]:
    """
    Quick function to get next optimal posting time with rationale

    Returns:
        Tuple of (posting_time, rationale)
    """
    analyzer = OptimalPostingTimesAnalyzer(db)
    posting_time = analyzer.get_next_optimal_time(user_id, start_from)
    rationale = analyzer.get_posting_rationale(posting_time, user_id)

    return posting_time, rationale
