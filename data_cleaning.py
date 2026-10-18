from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
RAW_DIR = ROOT_DIR / "data" / "raw"
OUTPUT_DIR = ROOT_DIR / "data" / "cleaned" / "generated"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

COLUMNS = ["co", "no2", "o3", "pm10", "pm25", "so2", "aqi"]

CITIES = {
    "Delhi": "delhi_aqi_.csv",
    "Faridabad": "faridabad_aqi_.csv",
    "Gurugram": "gurugram_aqi_.csv",
}


def clean_data(city, filename):
    input_path = RAW_DIR / filename

    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    df = pd.read_csv(input_path)

    missing = [col for col in COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"{city}: Missing columns {missing}")

    outliers = pd.Series(False, index=df.index)

    for col in COLUMNS:
        values = pd.to_numeric(df[col], errors="coerce")
        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        outliers |= ((values < lower) | (values > upper)).fillna(False)

    cleaned_df = df.loc[~outliers].copy()

    output_file = OUTPUT_DIR / f"{city.lower()}_aqi_2022_2023_cleaned.csv"
    cleaned_df.to_csv(output_file, index=False)

    return {
        "City": city,
        "Original Rows": len(df),
        "Removed Rows": int(outliers.sum()),
        "Cleaned Rows": len(cleaned_df),
    }


def main():
    results = []

    for city, filename in CITIES.items():
        result = clean_data(city, filename)
        results.append(result)
        print(result)

    report = pd.DataFrame(results)
    report.to_csv(OUTPUT_DIR / "cleaning_report.csv", index=False)

    print("\nData cleaning completed!")


if __name__ == "__main__":
    main()