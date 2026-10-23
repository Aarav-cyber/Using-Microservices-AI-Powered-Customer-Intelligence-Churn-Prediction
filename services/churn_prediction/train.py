from pathlib import Path
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "saas"
TRAIN_PATH = DATA_DIR / "train.csv"
TEST_PATH = DATA_DIR / "test.csv"
MODEL_PATH = BASE_DIR / "model" / "churn_model.joblib"

# --------------------------------------------------
# Features used by the SaaS churn model
# --------------------------------------------------
NUMERIC_FEATURES = [
    "account_age_days",
    "monthly_price_usd",
    "support_tickets_90d",
    "days_since_last_login",
]

CATEGORICAL_FEATURES = [
    "plan_tier",
]

FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "churned"


def load_dataset(path: Path) -> pd.DataFrame:
    """Load a CSV and validate the required columns."""
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    df = pd.read_csv(path)
    required_columns = FEATURES + [TARGET]
    missing = set(required_columns) - set(df.columns)
    if missing:
        raise ValueError(
            f"{path.name} is missing required columns: {sorted(missing)}"
        )
    if df.empty:
        raise ValueError(f"{path.name} contains no rows.")
    if df[FEATURES].isna().all(axis=1).any():
        raise ValueError(
            f"{path.name} contains rows with all model features missing."
        )
    if df[TARGET].isna().any():
        raise ValueError(
            f"{path.name} contains missing churn labels."
        )
    labels = set(df[TARGET].unique())
    if not labels.issubset({0, 1}):
        raise ValueError(
            f"{path.name}: '{TARGET}' must contain only 0 and 1. Found: {labels}"
        )
    df[TARGET] = df[TARGET].astype(int)
    return df


def main():
    train_df = load_dataset(TRAIN_PATH)
    test_df = load_dataset(TEST_PATH)

    print(f"Loaded {len(train_df)} training rows and {len(test_df)} test rows.")

    X_train = train_df[FEATURES]
    y_train = train_df[TARGET]

    X_test = test_df[FEATURES]
    y_test = test_df[TARGET]

    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, NUMERIC_FEATURES),
            ("cat", categorical_transformer, CATEGORICAL_FEATURES),
        ]
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", LogisticRegression(max_iter=1000, random_state=42)),
        ]
    )

    print("Training SaaS churn prediction model...")
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    y_prob = pipeline.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    roc_auc = roc_auc_score(y_test, y_prob)

    print("\n--- Model Evaluation (SaaS Test Set) ---")
    print(f"Accuracy:  {acc:.4f}")
    print(f"Precision: {prec:.4f}")
    print(f"Recall:    {rec:.4f}")
    print(f"F1-Score:  {f1:.4f}")
    print(f"ROC-AUC:   {roc_auc:.4f}")

    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, digits=4))

    print("Confusion Matrix:")
    print(confusion_matrix(y_test, y_pred))

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)
    print(f"\nModel saved to: {MODEL_PATH}")

    # Artifact verification
    loaded_model = joblib.load(MODEL_PATH)
    sample = X_test.iloc[[0]]
    sample_pred = loaded_model.predict_proba(sample)[0, 1]
    assert 0.0 <= sample_pred <= 1.0, "Prediction out of range"
    print("Artifact verification passed.")


if __name__ == "__main__":
    main()
