from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()


def analyze_sentiment(message: str) -> dict:
    scores = analyzer.polarity_scores(message)
    if scores["compound"] >= 0.05:
        sentiment = "positive"
    elif scores["compound"] <= -0.05:
        sentiment = "negative"
    else:
        sentiment = "neutral"
    return {
        "sentiment": sentiment,
        "positive_score": scores["pos"],
        "neutral_score": scores["neu"],
        "negative_score": scores["neg"],
        "compound_score": scores["compound"],
    }
