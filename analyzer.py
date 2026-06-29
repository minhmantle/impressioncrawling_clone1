"""
analyzer.py — Fake engagement scoring engine
Dùng X API Basic tier (tweepy) để phân tích likers/retweeters
"""

import tweepy
from datetime import datetime, timezone

BASELINE = {
    "like_per_view":   0.025,
    "rt_per_like":     0.15,
    "reply_per_like":  0.10,
}


class TweetAnalyzer:
    def __init__(self, client: tweepy.Client):
        self.client = client

    def analyze(self, tweet_id: str, max_likers: int = 100, max_retweeters: int = 100) -> dict | None:
        try:
            resp = self.client.get_tweet(
                tweet_id,
                tweet_fields=["public_metrics", "created_at", "author_id", "lang"],
                expansions=["author_id"],
                user_fields=["public_metrics", "created_at", "description", "profile_image_url"],
            )
        except tweepy.errors.TweepyException as e:
            raise Exception(f"Tweet fetch failed: {e}")

        if not resp.data:
            return None

        tweet   = resp.data
        metrics = tweet.public_metrics or {}

        likers      = self._fetch_users(self.client.get_liking_users, tweet_id, max_likers)
        retweeters  = self._fetch_users(self.client.get_retweeters,   tweet_id, max_retweeters)

        seen, unique = set(), []
        for u in likers + retweeters:
            if u.id not in seen:
                seen.add(u.id)
                unique.append(u)

        user_stats, bot_flags = self._analyze_users(unique)
        bot_pct = len(bot_flags) / max(len(unique), 1)

        return {
            "tweet_id":        tweet_id,
            "author_id":       str(tweet.author_id),
            "created_at":      tweet.created_at.isoformat() if tweet.created_at else None,
            "lang":            tweet.lang,
            "metrics": {
                "impression_count": metrics.get("impression_count"),
                "like_count":       metrics.get("like_count"),
                "retweet_count":    metrics.get("retweet_count"),
                "reply_count":      metrics.get("reply_count"),
                "quote_count":      metrics.get("quote_count"),
                "bookmark_count":   metrics.get("bookmark_count"),
            },
            "likers_fetched":     len(likers),
            "retweeters_fetched": len(retweeters),
            "analyzed_users":     len(unique),
            "bot_account_pct":    bot_pct,
            "bot_flags":          bot_flags[:20],
            "user_stats":         user_stats,
        }

    def _fetch_users(self, method, tweet_id, max_results):
        users = []
        try:
            for page in tweepy.Paginator(
                method, tweet_id,
                user_fields=["public_metrics", "created_at", "description",
                             "profile_image_url", "entities"],
                max_results=100,
            ):
                if not page.data:
                    break
                users.extend(page.data)
                if len(users) >= max_results:
                    break
        except tweepy.errors.TweepyException:
            pass
        return users[:max_results]

    def _analyze_users(self, users):
        now   = datetime.now(timezone.utc)
        stats = dict(age_under_30d=0, age_30_180d=0, age_180_365d=0,
                     age_over_1yr=0, no_bio=0, no_avatar=0,
                     low_followers=0, low_tweets=0)
        bot_flags = []

        for user in users:
            score, flags = 0, []

            if user.created_at:
                age = (now - user.created_at).days
                if age < 30:
                    stats["age_under_30d"] += 1; score += 3; flags.append("new_account")
                elif age < 180:
                    stats["age_30_180d"]   += 1; score += 1; flags.append("fresh_account")
                elif age < 365:
                    stats["age_180_365d"]  += 1
                else:
                    stats["age_over_1yr"]  += 1

            if not user.description or len(user.description.strip()) < 5:
                stats["no_bio"]    += 1; score += 1; flags.append("no_bio")

            if not user.profile_image_url or "default_profile" in (user.profile_image_url or ""):
                stats["no_avatar"] += 1; score += 2; flags.append("no_avatar")

            pub       = user.public_metrics or {}
            followers = pub.get("followers_count", 0)
            tweets    = pub.get("tweet_count", 0)
            following = pub.get("following_count", 0)

            if followers < 10:
                stats["low_followers"] += 1; score += 2; flags.append("low_followers")
            if tweets < 10:
                stats["low_tweets"]    += 1; score += 2; flags.append("low_tweets")
            if followers > 0 and following / max(followers, 1) > 10:
                score += 1; flags.append("follow_ratio")

            if score >= 3:
                bot_flags.append({"username": user.username, "bot_score": score, "flags": flags})

        return stats, bot_flags


class FakeScoreEngine:
    def score(self, result: dict) -> dict:
        m        = result["metrics"]
        views    = m.get("impression_count") or 0
        likes    = m.get("like_count")       or 0
        rts      = m.get("retweet_count")    or 0
        replies  = m.get("reply_count")      or 0
        total    = 0
        breakdown = []

        # Signal 1 — Like/View ratio
        if views > 0 and likes > 0:
            lvr = likes / views
            if lvr < 0.002:
                flag, pts, detail = "HIGH", 25, f"Like/View = {lvr:.3%} — suspiciously low, possible view inflation"
            elif lvr > 0.15:
                flag, pts, detail = "MEDIUM", 15, f"Like/View = {lvr:.3%} — unusually high, possible like-buying"
            else:
                flag, pts, detail = "OK", 0, f"Like/View = {lvr:.3%} — within normal range"
        else:
            flag, pts, detail = "N/A", 0, "Not enough data"
        breakdown.append({"name": "Like / View Ratio", "flag": flag, "contribution": pts, "detail": detail})
        total += pts

        # Signal 2 — RT/Like ratio
        if likes > 0:
            rtlr = rts / likes
            if rtlr > 0.8:
                flag, pts, detail = "HIGH",   20, f"RT/Like = {rtlr:.2%} — very high, RT farming likely"
            elif rtlr > 0.4:
                flag, pts, detail = "MEDIUM", 10, f"RT/Like = {rtlr:.2%} — elevated"
            else:
                flag, pts, detail = "OK",      0, f"RT/Like = {rtlr:.2%} — normal"
        else:
            flag, pts, detail = "N/A", 0, "No likes data"
        breakdown.append({"name": "Retweet / Like Ratio", "flag": flag, "contribution": pts, "detail": detail})
        total += pts

        # Signal 3 — Reply depth
        if likes > 200:
            rr = replies / max(likes, 1)
            if rr < 0.005:
                flag, pts, detail = "HIGH",   20, f"Reply/Like = {rr:.3%} — bots rarely reply"
            elif rr < 0.02:
                flag, pts, detail = "MEDIUM", 10, f"Reply/Like = {rr:.3%} — low"
            else:
                flag, pts, detail = "OK",      0, f"Reply/Like = {rr:.3%} — organic"
        else:
            flag, pts, detail = "N/A", 0, "Too few likes to assess"
        breakdown.append({"name": "Reply Engagement Depth", "flag": flag, "contribution": pts, "detail": detail})
        total += pts

        # Signal 4 — Account quality
        bot_pct   = result.get("bot_account_pct", 0)
        analyzed  = result.get("analyzed_users",  0)
        if analyzed < 20:
            flag, pts, detail = "N/A",    0, "Too few accounts analyzed"
        elif bot_pct > 0.6:
            flag, pts, detail = "HIGH",   30, f"{bot_pct:.0%} of analyzed accounts show bot signals"
        elif bot_pct > 0.35:
            flag, pts, detail = "MEDIUM", 15, f"{bot_pct:.0%} of accounts have suspicious patterns"
        elif bot_pct > 0.15:
            flag, pts, detail = "LOW",     5, f"{bot_pct:.0%} of accounts flagged — slightly elevated"
        else:
            flag, pts, detail = "OK",      0, f"{bot_pct:.0%} of accounts flagged — looks clean"
        breakdown.append({"name": "Engager Account Quality", "flag": flag, "contribution": pts, "detail": detail})
        total += pts

        # Signal 5 — Absolute volume (hackathon context)
        if views > 500_000:
            flag, pts, detail = "HIGH",   20, f"{views:,} views — extreme for a hackathon tweet"
        elif views > 100_000 or likes > 10_000:
            flag, pts, detail = "MEDIUM", 10, f"Views={views:,} / Likes={likes:,} — high for hackathon context"
        else:
            flag, pts, detail = "OK",      0, "Volume looks proportionate"
        breakdown.append({"name": "Absolute Volume Check", "flag": flag, "contribution": pts, "detail": detail})
        total += pts

        total = min(total, 100)

        if total >= 70:
            verdict = "🔴 CHEATING DETECTED"
        elif total >= 40:
            verdict = "🟡 SUSPICIOUS"
        else:
            verdict = "🟢 CLEAN"

        return {
            "total_score": total,
            "verdict":     verdict,
            "breakdown":   breakdown,
            "ratios": {
                "like_per_view":  likes   / max(views, 1),
                "rt_per_like":    rts     / max(likes, 1),
                "reply_per_like": replies / max(likes, 1),
            }
        }
