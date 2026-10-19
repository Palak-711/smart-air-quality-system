# -*- coding: utf-8 -*-
"""
Real-time Sensor Data Inference Module for Backend Services
Project: Smart Air Quality Monitoring & Prediction System

Description:
    This module provides production-grade inference functions for backend systems.
    It loads the pre-trained DCAE model and feature scaler to sanitize live incoming
    raw sensor readings in real-time.
"""

import os
import numpy as np
import pandas as pd
import joblib
from tensorflow.keras.models import load_model

# Define artifact paths
MODEL_FILE_PATH = 'models/best_dcae_sensor_model.h5'
SCALER_FILE_PATH = 'models/scaler.pkl'

def calibrate_incoming_sensor_data(raw_input_df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitizes and calibrates incoming raw environmental sensor dataframes.

    Parameters:
        raw_input_df (pd.DataFrame): DataFrame containing raw pollutant columns
                                     ['pm25', 'pm10', 'co', 'no2', 'so2'].

    Returns:
        pd.DataFrame: A copy of the input dataframe with noise-filtered,
                      calibrated ground-truth pollutant values.
    """

    # 1. Artifact Integrity Verification
    if not os.path.exists(MODEL_FILE_PATH):
        raise FileNotFoundError(f"Critical Error: Trained model weights missing at '{MODEL_FILE_PATH}'.")
    if not os.path.exists(SCALER_FILE_PATH):
        raise FileNotFoundError(f"Critical Error: Feature scaler artifact missing at '{SCALER_FILE_PATH}'.")

    # 2. Load Model Weights & Scaler
    inference_model = load_model(MODEL_FILE_PATH)
    feature_scaler = joblib.load(SCALER_FILE_PATH)

    # 3. Schema Validation
    required_features = ['pm25', 'pm10', 'co', 'no2', 'so2']
    for feature in required_features:
        if feature not in raw_input_df.columns:
            raise ValueError(f"Data Schema Error: Missing required sensor column '{feature}'.")

    raw_sensor_values = raw_input_df[required_features].values

    # 4. Feature Normalization using Training Scaler
    scaled_input_matrix = feature_scaler.transform(raw_sensor_values)

    # 5. Tensor Reshaping for 1D Convolutional Network: (Samples, Timesteps, Features)
    tensor_input = np.expand_dims(scaled_input_matrix, axis=1)

    # 6. Model Prediction / Noise Reconstruction
    reconstructed_tensor = inference_model.predict(tensor_input)
    reconstructed_matrix_2d = reconstructed_tensor.squeeze(axis=1)

    # 7. Inverse Scaling to Real-World Physical Units
    calibrated_physical_values = feature_scaler.inverse_transform(reconstructed_matrix_2d)

    # 8. Construct Output DataFrame
    sanitized_output_df = raw_input_df.copy()
    sanitized_output_df[required_features] = calibrated_physical_values

    print("[SUCCESS] Live incoming sensor payload successfully calibrated.")
    return sanitized_output_df