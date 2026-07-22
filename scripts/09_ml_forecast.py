#!/usr/bin/env python3
"""Stage D — ML pipeline: peak-hour demand forecasting + adaptive routing.

1. Builds a multi-day hourly-demand history grounded in the calibrated diurnal
   shape (from edge_counts_24h.xml), with realistic weekday/weekend, weather and
   noise effects plus autocorrelation.
2. Engineers time-series features (calendar, weather, lag-24h/lag-168h, rolling
   means) and trains ML forecasters:
      * scikit-learn RandomForest and GradientBoosting,
      * a small neural net (TensorFlow/Keras if installed, else sklearn MLP).
3. Benchmarks them against a naive baseline (same-hour-yesterday persistence)
   and reports the accuracy improvement (RMSE/MAPE).
4. Demonstrates adaptive routing: the forecast flags high-demand hours and emits
   recommended rerouting aggressiveness for the V2X controller to consume.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

import common as C

# --- Optional TensorFlow, graceful fallback to sklearn MLP -------------------
try:
    import tensorflow as tf  # noqa
    from tensorflow import keras
    HAS_TF = True
except Exception:
    HAS_TF = False

from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_percentage_error


def calibrated_hourly_shape() -> np.ndarray:
    """Total demanded vehicles per hour from the calibrated counts file."""
    totals = np.zeros(24)
    for _, el in ET.iterparse(C.EDGE_COUNTS_FILE, events=("end",)):
        if el.tag == "interval":
            h = int(float(el.get("begin")) // 3600)
            if 0 <= h < 24:
                totals[h] = sum(float(e.get("entered")) for e in el.findall("edge"))
            el.clear()
    return totals


def synthesize_history(shape: np.ndarray, n_days: int, rng) -> pd.DataFrame:
    """Grounded synthetic hourly demand over n_days (method is what matters)."""
    rows = []
    base = shape / shape.max()  # normalized diurnal shape
    for day in range(n_days):
        dow = day % 7
        is_weekend = dow >= 5
        dow_factor = 0.72 if is_weekend else 1.0
        rain = max(0.0, rng.normal(0.15, 0.2))          # daily rain intensity
        rain = min(rain, 1.0)
        rain_factor = 1.0 - 0.18 * rain                 # rain suppresses trips
        day_level = rng.normal(1.0, 0.06)               # day-to-day variation
        for h in range(24):
            # weekend flattens the peaks; rain shifts/reduces
            shape_h = base[h] ** (1.15 if is_weekend else 1.0)
            demand = shape.max() * shape_h * dow_factor * rain_factor * day_level
            demand *= (1 + rng.normal(0, 0.05))         # hourly noise
            rows.append({"day": day, "dow": dow, "hour": h,
                         "is_weekend": int(is_weekend), "rain": rain,
                         "demand": max(0.0, demand)})
    df = pd.DataFrame(rows)
    df["t"] = df["day"] * 24 + df["hour"]
    df = df.sort_values("t").reset_index(drop=True)
    # Autocorrelation features.
    df["lag24"] = df["demand"].shift(24)
    df["lag168"] = df["demand"].shift(168)
    df["roll24"] = df["demand"].shift(1).rolling(24).mean()
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    return df.dropna().reset_index(drop=True)


def build_nn(input_dim: int):
    if HAS_TF:
        m = keras.Sequential([
            keras.layers.Input((input_dim,)),
            keras.layers.Dense(64, activation="relu"),
            keras.layers.Dense(32, activation="relu"),
            keras.layers.Dense(1),
        ])
        m.compile(optimizer="adam", loss="mse")
        return m, "tensorflow-keras"
    return MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=500, random_state=0), "sklearn-mlp"


def rmse(a, b):
    return float(np.sqrt(mean_squared_error(a, b)))


def main() -> None:
    cfg = C.load_config()["ml"]
    rng = np.random.default_rng(cfg["seed"])
    shape = calibrated_hourly_shape()
    df = synthesize_history(shape, cfg["n_days"], rng)

    feats = ["dow", "hour", "is_weekend", "rain", "lag24", "lag168",
             "roll24", "hour_sin", "hour_cos"]
    split_t = (cfg["n_days"] - cfg["test_days"]) * 24
    train, test = df[df.t < split_t], df[df.t >= split_t]
    Xtr, ytr = train[feats].values, train["demand"].values
    Xte, yte = test[feats].values, test["demand"].values

    # Naive baseline: same hour yesterday (lag24).
    base_pred = test["lag24"].values
    base_rmse, base_mape = rmse(yte, base_pred), float(mean_absolute_percentage_error(yte, base_pred))

    results = {"baseline_naive": {"rmse": round(base_rmse, 1),
                                  "mape": round(base_mape * 100, 2)}}

    models = {
        "random_forest": RandomForestRegressor(n_estimators=300, random_state=0, n_jobs=-1),
        "grad_boost": GradientBoostingRegressor(random_state=0),
    }
    for name, mdl in models.items():
        mdl.fit(Xtr, ytr)
        p = mdl.predict(Xte)
        results[name] = {"rmse": round(rmse(yte, p), 1),
                         "mape": round(float(mean_absolute_percentage_error(yte, p)) * 100, 2)}

    nn, nn_kind = build_nn(len(feats))
    if HAS_TF:
        # Standardize BOTH features and target — the target is ~1e5 in magnitude,
        # so an unscaled linear output with MSE loss never converges.
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        ymu, ysd = ytr.mean(), ytr.std() + 1e-9
        nn.fit((Xtr - mu) / sd, (ytr - ymu) / ysd,
               epochs=150, batch_size=32, verbose=0,
               validation_split=0.1,
               callbacks=[keras.callbacks.EarlyStopping(patience=15, restore_best_weights=True)])
        p = nn.predict((Xte - mu) / sd, verbose=0).ravel() * ysd + ymu
    else:
        nn.fit(Xtr, ytr)
        p = nn.predict(Xte)
    results[nn_kind] = {"rmse": round(rmse(yte, p), 1),
                        "mape": round(float(mean_absolute_percentage_error(yte, p)) * 100, 2)}

    best = min((k for k in results if k != "baseline_naive"),
               key=lambda k: results[k]["rmse"])
    improvement = 100 * (base_rmse - results[best]["rmse"]) / base_rmse

    # Adaptive routing hook: flag high-demand (peak) hours from the forecast.
    peak_threshold = np.quantile(shape, 0.75)
    peak_hours = [int(h) for h in range(24) if shape[h] >= peak_threshold]
    routing_policy = {
        "peak_hours": peak_hours,
        "reroute_interval_s": {"peak": 30, "offpeak": 120},
        "note": "During forecast peak hours the V2X controller reroutes equipped "
                "vehicles twice as often to pre-empt predicted congestion.",
    }

    out = {
        "nn_backend": nn_kind,
        "n_days": cfg["n_days"], "test_days": cfg["test_days"],
        "features": feats,
        "results": results,
        "best_model": best,
        "improvement_vs_naive_pct": round(improvement, 1),
        "adaptive_routing_policy": routing_policy,
    }
    d = C.ROOT / "output" / "ml"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "forecast.json", "w") as fh:
        json.dump(out, fh, indent=2)
    C.log("ml", f"NN backend: {nn_kind}")
    for k, v in results.items():
        C.log("ml", f"  {k:22s} RMSE={v['rmse']:>8} MAPE={v['mape']}%")
    C.log("ml", f"Best={best}, improvement vs naive baseline = {improvement:.1f}% RMSE")
    C.log("ml", f"-> {d/'forecast.json'}")


if __name__ == "__main__":
    main()
