"""
Hızlı diagnostik script - Score'ları ve threshold'u kontrol eder.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

# Load config
env_file = Path(__file__).parent / ".env"
load_dotenv(env_file)

# Get config values
min_score = float(os.getenv("STRATEGY_MIN_SCORE", "7.0"))
weights = {
    'volume_profile': float(os.getenv("WEIGHT_VOLUME_PROFILE", "2.0")),
    'orderbook': float(os.getenv("WEIGHT_ORDERBOOK", "2.0")),
    'cvd': float(os.getenv("WEIGHT_CVD", "2.0")),
    'supply_demand': float(os.getenv("WEIGHT_SUPPLY_DEMAND", "2.0")),
    'hvn_support': float(os.getenv("WEIGHT_HVN", "1.0")),
    'time_of_day': float(os.getenv("WEIGHT_TIME_OF_DAY", "1.0"))
}

max_score = sum(weights.values())

print("=" * 60)
print("STRATEGY CONFIGURATION CHECK")
print("=" * 60)
print(f"\nMinimum Score Threshold: {min_score:.1f}")
print(f"Maximum Possible Score: {max_score:.1f}")
print(f"Threshold Percentage: {(min_score/max_score)*100:.1f}%")
print("\nWeight Configuration:")
for factor, weight in weights.items():
    print(f"   {factor:20s}: {weight:.1f}")

print("\n" + "=" * 60)
print("DIAGNOSTIC INFO")
print("=" * 60)

# Calculate scenarios
print("\nScore Scenarios:")
print(f"\n1. Tum faktorler aktif (mukemmel durum):")
print(f"   Max Score: {max_score:.1f}")
print(f"   Threshold: {min_score:.1f}")
signal1 = "EVET" if max_score >= min_score else "HAYIR"
print(f"   Sinyal uretilir: {signal1}")

print(f"\n2. Yari faktorler aktif (orta durum):")
half_score = max_score / 2
print(f"   Score: {half_score:.1f}")
print(f"   Threshold: {min_score:.1f}")
signal2 = "EVET" if half_score >= min_score else "HAYIR"
print(f"   Sinyal uretilir: {signal2}")

print(f"\n3. Birkac faktor aktif (zayif durum):")
few_score = max_score * 0.3
print(f"   Score: {few_score:.1f}")
print(f"   Threshold: {min_score:.1f}")
signal3 = "EVET" if few_score >= min_score else "HAYIR"
print(f"   Sinyal uretilir: {signal3}")

print("\n" + "=" * 60)
print("RECOMMENDATIONS")
print("=" * 60)

if min_score >= max_score * 0.8:
    print("\nWARNING: Threshold cok yuksek! (>80% of max)")
    print("   Onerilen: 5.0 - 7.0")
    print(f"   Su anki: {min_score:.1f}")
elif min_score >= max_score * 0.7:
    print("\nOK: Threshold dengeli (70-80% of max)")
    print("   Bu ayar konservatif ama makul")
elif min_score >= max_score * 0.5:
    print("\nOK: Threshold orta seviye (50-70% of max)")
    print("   Bu ayar daha fazla sinyal uretir")
else:
    print("\nWARNING: Threshold dusuk (<50% of max)")
    print("   Daha fazla sinyal ama daha fazla risk!")

print("\nTIP: Eger hic trade yapilmiyorsa:")
print("   1. Dashboard'da 'Last Scores' degerlerini kontrol edin")
print("   2. Score'lar threshold'un altindaysa threshold'u dusurun")
print("   3. Veya weight'leri artirin")
test_threshold = max_score * 0.4
print(f"\n   Test icin threshold'u {test_threshold:.1f} yapabilirsiniz")

print("\n" + "=" * 60)
