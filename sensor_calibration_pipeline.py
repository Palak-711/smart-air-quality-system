# -*- coding: utf-8 -*-
"""
Deep Convolutional Autoencoder (DCAE) for Sensor Calibration & Noise Filtering
Project: Smart Air Quality Monitoring & Prediction System

Description:
    This script handles the unsupervised learning pipeline for environmental sensor calibration.
    It combines multi-city AQI datasets, normalizes sensor features, trains a 1D Convolutional
    Autoencoder to remove measurement noise/drift, saves model artifacts, and exports
    calibrated ground-truth datasets.
"""

import os
import numpy as np
import pandas as pd
import joblib
import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Conv1D, MaxPooling1D, UpSampling1D
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
from sklearn.preprocessing import MinMaxScaler

# Display execution header
print("="*70)
print("AIR QUALITY SENSOR CALIBRATION & NOISE FILTERING PIPELINE")
print("="*70)

# ==========================================
# 1. DATA INGESTION & AGGREGATION
# ==========================================
city_files = [
    'delhi_aqi_2022_2023_cleaned (1).csv',
    'faridabad_aqi_2022_2023_cleaned (1).csv',
    'gurugram_aqi_2022_2023_cleaned (1).csv'
]

data_frames = []
for file_path in city_files:
    if os.path.exists(file_path):
        temp_df = pd.read_csv(file_path)
        data_frames.append(temp_df)
        print(f"[INFO] Successfully loaded dataset: {file_path} ({len(temp_df)} records)")
    else:
        print(f"[WARNING] Target file not found: {file_path}")

if not data_frames:
    raise FileNotFoundError("Critical Error: No valid city dataset files detected.")

# Combine all city dataframes into a unified master frame
master_df = pd.concat(data_frames, ignore_index=True)

# Define primary pollutant features targeted for calibration
target_features = ['pm25', 'pm10', 'co', 'no2', 'so2']
sensor_matrix = master_df[target_features].values

print(f"\n[SUMMARY] Total aggregated records across all regions: {sensor_matrix.shape[0]}")
print(f"[SUMMARY] Target calibration features: {target_features}")

# ==========================================
# 2. FEATURE SCALING & NORMALIZATION
# ==========================================
print("\n[INFO] Initializing MinMaxScaler for feature normalization (Range: [0, 1])...")
feature_scaler = MinMaxScaler()
normalized_sensor_data = feature_scaler.fit_transform(sensor_matrix)

# Ensure output directory exists for saved artifacts
os.makedirs('models', exist_ok=True)
scaler_output_path = 'models/scaler.pkl'
joblib.dump(feature_scaler, scaler_output_path)
print(f"[SUCCESS] Feature scaler successfully persisted at: {scaler_output_path}")

# ==========================================
# 3. TENSOR RESHAPING FOR CONV1D ARCHITECTURE
# ==========================================
# Reshaping 2D array into 3D tensor format required by Conv1D layers: (Samples, Timesteps, Features)
training_tensor = np.expand_dims(normalized_sensor_data, axis=1)
print(f"[INFO] Generated 3D training tensor shape for DCAE: {training_tensor.shape}")

# ==========================================
# 4. DCAE MODEL ARCHITECTURE CONSTRUCTION
# ==========================================
print("\n[INFO] Constructing Deep Convolutional Autoencoder (DCAE) network topology...")
input_layer = Input(shape=(training_tensor.shape[1], training_tensor.shape[2]))

# --- Encoder Path ---
encoder_layer = Conv1D(filters=32, kernel_size=1, activation='relu', padding='same')(input_layer)
encoded_representation = MaxPooling1D(pool_size=1, padding='same')(encoder_layer)

# --- Decoder Path ---
decoder_layer = Conv1D(filters=32, kernel_size=1, activation='relu', padding='same')(encoded_representation)
decoded_output = UpSampling1D(size=1)(decoder_layer)
output_layer = Conv1D(filters=training_tensor.shape[2], kernel_size=1, activation='sigmoid', padding='same')(decoded_output)

# Compile Autoencoder Model
autoencoder_model = Model(inputs=input_layer, outputs=output_layer)
autoencoder_model.compile(optimizer='adam', loss='mean_squared_error', metrics=['mae'])

autoencoder_model.summary()

# ==========================================
# 5. MODEL TRAINING WITH OPTIMIZATION CALLBACKS
# ==========================================
print("\n[INFO] Commencing model training routine with Early Stopping...")

model_save_path = 'models/best_dcae_sensor_model.h5'
training_callbacks = [
    EarlyStopping(monitor='val_loss', patience=3, restore_best_weights=True, verbose=1),
    ModelCheckpoint(filepath=model_save_path, monitor='val_loss', save_best_only=True, verbose=1)
]

history = autoencoder_model.fit(
    x=training_tensor,
    y=training_tensor,
    epochs=25,
    batch_size=64,
    shuffle=True,
    validation_split=0.15,
    callbacks=training_callbacks,
    verbose=1
)

print("\n[SUCCESS] DCAE model training completed successfully.")

# ==========================================
# 6. DATA RECONSTRUCTION & CALIBRATION
# ==========================================
print("\n[INFO] Executing data reconstruction to filter sensor noise...")
reconstructed_scaled_tensor = autoencoder_model.predict(training_tensor)
reconstructed_scaled_2d = reconstructed_scaled_tensor.squeeze(axis=1)

# Reverse transformation back to original physical measurement scale
calibrated_sensor_values = feature_scaler.inverse_transform(reconstructed_scaled_2d)

# Inject calibrated values back into the master dataframe
master_df[target_features] = calibrated_sensor_values

# Save master calibrated dataset
master_output_file = 'fully_calibrated_sensor_data.csv'
master_df.to_csv(master_output_file, index=False)
print(f"[SUCCESS] Master calibrated dataset exported as: {master_output_file}")

# ==========================================
# 7. REGIONAL DATA PARTITIONING
# ==========================================
print("\n[INFO] Partitioning master dataset into region-specific calibrated files...")

if 'location_name' in master_df.columns:
    distinct_locations = master_df['location_name'].unique()
    print(f"[INFO] Identified distinct regions: {list(distinct_locations)}")

    for region in distinct_locations:
        regional_df = master_df[master_df['location_name'] == region]
        clean_region_name = str(region).lower().replace(' ', '_')
        region_filename = f"{clean_region_name}_fully_calibrated.csv"

        regional_df.to_csv(region_filename, index=False)
        print(f"  -> Exported: {region_filename} ({len(regional_df)} records)")
else:
    print("[WARNING] 'location_name' column missing. Regional partitioning skipped.")

print("\n" + "="*70)
print("PIPELINE EXECUTION SUCCESSFUL. ALL ARTIFACTS GENERATED.")
print("="*70)