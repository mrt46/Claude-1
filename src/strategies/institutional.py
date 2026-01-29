"""
Institutional Multi-Factor Strategy.

Combines all advanced analysis into a weighted scoring system.
"""

from datetime import datetime
from typing import Dict, Optional

import pandas as pd

from src.analysis.cvd import VolumeDeltaAnalyzer
from src.analysis.microstructure import MarketMicrostructure
from src.analysis.orderbook import OrderBook, OrderBookAnalyzer
from src.analysis.supply_demand import SupplyDemandZones
from src.analysis.volume_profile import VolumeProfileAnalyzer
from src.core.logger import get_logger
from src.data.market_data import MarketDataManager
from src.strategies.base import BaseStrategy, Signal

logger = get_logger(__name__)


class InstitutionalStrategy(BaseStrategy):
    """
    Professional multi-factor strategy.
    
    Combines ALL advanced analysis:
    1. Volume Profile (POC, VAH, VAL, HVN)
    2. Order Book (imbalance, walls, liquidity)
    3. CVD (divergence detection)
    4. Supply/Demand zones
    5. Microstructure (spread, slippage)
    
    Decision: Multi-factor scoring (need 7/10 minimum)
    """
    
    def __init__(self, config: Dict):
        """
        Initialize institutional strategy.
        
        Args:
            config: Strategy configuration with weights and min_score
        """
        super().__init__("InstitutionalStrategy", config)
        
        # Initialize all analyzers
        self.vp_analyzer = VolumeProfileAnalyzer()
        self.ob_analyzer = OrderBookAnalyzer()
        self.cvd_analyzer = VolumeDeltaAnalyzer()
        self.sd_analyzer = SupplyDemandZones()
        self.micro_analyzer = MarketMicrostructure()
        
        # Scoring weights
        self.weights = config.get('weights', {
            'volume_profile': 2.0,
            'orderbook': 2.0,
            'cvd': 2.0,
            'supply_demand': 2.0,
            'hvn_support': 1.0,
            'time_of_day': 1.0
        })
        
        self.min_score = config.get('min_score', 7.0)
        # Separate thresholds for BUY and SELL (optional)
        self.min_buy_score = config.get('min_buy_score', self.min_score)
        self.min_sell_score = config.get('min_sell_score', self.min_score)
        self.market_data_manager: Optional[MarketDataManager] = None
        
        # Store last analysis scores for dashboard
        self._last_buy_score: float = 0.0
        self._last_sell_score: float = 0.0
        self._last_max_score: float = sum(self.weights.values())
    
    def set_market_data_manager(self, manager: MarketDataManager) -> None:
        """Set market data manager for real-time data."""
        self.market_data_manager = manager
    
    async def generate_signal(
        self,
        df: pd.DataFrame,
        order_book: Optional[OrderBook] = None,
        **kwargs
    ) -> Optional[Signal]:
        """
        Generate signal using multi-factor analysis.
        
        Args:
            df: OHLCV DataFrame
            order_book: Optional OrderBook object
            **kwargs: Additional data
        
        Returns:
            Signal or None
        """
        if df.empty:
            return None
        
        symbol = df['symbol'].iloc[0] if 'symbol' in df.columns else 'UNKNOWN'
        current_price = float(df['close'].iloc[-1])
        
        self.logger.info(f"Analyzing {symbol} at {current_price:.2f}")
        
        # ============ FACTOR 1: Volume Profile ============
        try:
            vp = self.vp_analyzer.calculate_volume_profile(df, period_hours=24)
            vp_position = self.vp_analyzer.get_current_position_in_profile(current_price, vp)
            nearest_hvn = self.vp_analyzer.find_nearest_hvn(current_price, vp)
        except Exception as e:
            self.logger.error(f"Volume profile analysis failed: {e}")
            return None
        
        # ============ FACTOR 2: Order Book ============
        if order_book is None:
            if self.market_data_manager:
                try:
                    ob_data = await self.market_data_manager.get_order_book_snapshot(symbol, limit=100)
                    order_book = OrderBook(
                        symbol=symbol,
                        bids=[(b[0], b[1]) for b in ob_data['bids']],
                        asks=[(a[0], a[1]) for a in ob_data['asks']],
                        timestamp=ob_data['timestamp']
                    )
                except Exception as e:
                    self.logger.error(f"Failed to fetch order book: {e}")
                    return None
            else:
                self.logger.warning("No order book provided and no market data manager")
                return None
        
        try:
            imbalance = self.ob_analyzer.calculate_imbalance(order_book)
            walls = self.ob_analyzer.detect_walls(order_book)
            liquidity = self.ob_analyzer.calculate_liquidity(order_book)
        except Exception as e:
            self.logger.error(f"Order book analysis failed: {e}")
            return None
        
        # ============ FACTOR 3: CVD ============
        cvd_divergence = None
        if self.market_data_manager:
            try:
                trades_df = await self.market_data_manager.get_recent_trades_data(symbol, limit=1000)
                if not trades_df.empty:
                    cvd_data = self.cvd_analyzer.calculate_cvd_from_trades(trades_df)
                    cvd_divergence = self.cvd_analyzer.calculate_cvd_divergence(df, cvd_data)
            except Exception as e:
                self.logger.warning(f"CVD analysis failed: {e}")
        
        if cvd_divergence is None:
            cvd_divergence = 'no_divergence'
        
        # ============ FACTOR 4: Supply/Demand ============
        try:
            demand_zones = self.sd_analyzer.find_demand_zones(df)
            supply_zones = self.sd_analyzer.find_supply_zones(df)
            
            # Update zone tests
            demand_zones = self.sd_analyzer.update_zone_tests(demand_zones, current_price)
            supply_zones = self.sd_analyzer.update_zone_tests(supply_zones, current_price)
            
            in_demand_zone = any(
                z.zone_low <= current_price <= z.zone_high and z.is_fresh
                for z in demand_zones
            )
            in_supply_zone = any(
                z.zone_low <= current_price <= z.zone_high and z.is_fresh
                for z in supply_zones
            )
        except Exception as e:
            self.logger.warning(f"Supply/demand analysis failed: {e}")
            in_demand_zone = False
            in_supply_zone = False
        
        # ============ FACTOR 5: Microstructure ============
        try:
            micro = await self.micro_analyzer.analyze_spread_and_liquidity(order_book)
            
            # Poor microstructure → reject immediately
            if micro['spread_quality'] == 'poor' or micro['liquidity_quality'] == 'poor':
                self.logger.warning(f"Poor microstructure (spread={micro['spread_quality']}, liquidity={micro['liquidity_quality']}), skipping trade")
                return None
        except Exception as e:
            self.logger.error(f"Microstructure analysis failed: {e}")
            return None
        
        # ============ SCORING SYSTEM ============
        buy_score = 0.0
        sell_score = 0.0
        max_score = sum(self.weights.values())
        
        # Factor 1: Volume Profile Position (weight: 2)
        if vp_position == 'below_val':
            buy_score += self.weights['volume_profile']
            self.logger.info(f"  ✓ Price below VAL (+{self.weights['volume_profile']})")
        elif vp_position == 'above_vah':
            sell_score += self.weights['volume_profile']
            self.logger.info(f"  ✓ Price above VAH (+{self.weights['volume_profile']} sell)")
        
        # Factor 2: Order Book Imbalance (weight: 2)
        if imbalance.interpretation == 'strong_buy_pressure':
            buy_score += self.weights['orderbook']
            self.logger.info(f"  ✓ Strong buy pressure (+{self.weights['orderbook']})")
        elif imbalance.interpretation == 'moderate_buy_pressure':
            buy_score += self.weights['orderbook'] / 2
            self.logger.info(f"  ✓ Moderate buy pressure (+{self.weights['orderbook']/2})")
        elif imbalance.interpretation == 'strong_sell_pressure':
            sell_score += self.weights['orderbook']
            self.logger.info(f"  ✓ Strong sell pressure (+{self.weights['orderbook']} sell)")
        elif imbalance.interpretation == 'moderate_sell_pressure':
            sell_score += self.weights['orderbook'] / 2
        
        # Factor 3: CVD Divergence (weight: 2)
        if cvd_divergence == 'bullish_divergence':
            buy_score += self.weights['cvd']
            self.logger.info(f"  ✓ Bullish CVD divergence (+{self.weights['cvd']})")
        elif cvd_divergence == 'bearish_divergence':
            sell_score += self.weights['cvd']
            self.logger.info(f"  ✓ Bearish CVD divergence (+{self.weights['cvd']} sell)")
        
        # Factor 4: Supply/Demand Zones (weight: 2)
        if in_demand_zone:
            buy_score += self.weights['supply_demand']
            self.logger.info(f"  ✓ In fresh demand zone (+{self.weights['supply_demand']})")
        if in_supply_zone:
            sell_score += self.weights['supply_demand']
            self.logger.info(f"  ✓ In fresh supply zone (+{self.weights['supply_demand']} sell)")
        
        # Factor 5: HVN Support/Resistance (weight: 1)
        if nearest_hvn:
            distance = abs(current_price - nearest_hvn) / current_price
            if distance < 0.005:  # Within 0.5%
                if current_price > nearest_hvn:
                    buy_score += self.weights['hvn_support']
                    self.logger.info(f"  ✓ HVN support at {nearest_hvn:.2f} (+{self.weights['hvn_support']})")
                else:
                    sell_score += self.weights['hvn_support']
                    self.logger.info(f"  ✓ HVN resistance at {nearest_hvn:.2f} (+{self.weights['hvn_support']} sell)")
        
        # Factor 6: Time of Day + Volume (weight: 1)
        # Simple implementation: check if recent volume is above average
        if len(df) >= 50:
            recent_volume = df['volume'].iloc[-10:].mean()
            avg_volume = df['volume'].iloc[-50:-10].mean()
            if recent_volume > avg_volume * 1.2:  # 20% above average
                # Amplify the winning side
                if buy_score > sell_score:
                    buy_score += self.weights['time_of_day']
                    self.logger.info(f"  ✓ High volume + buy bias (+{self.weights['time_of_day']})")
                elif sell_score > buy_score:
                    sell_score += self.weights['time_of_day']
                    self.logger.info(f"  ✓ High volume + sell bias (+{self.weights['time_of_day']})")
        
        # ============ DECISION ============
        self.logger.info(
            f"Final Scores: BUY={buy_score:.1f}/{max_score:.1f} (min: {self.min_buy_score:.1f}), "
            f"SELL={sell_score:.1f}/{max_score:.1f} (min: {self.min_sell_score:.1f})"
        )
        
        # Store scores for dashboard access (even if no signal)
        self._last_buy_score = buy_score
        self._last_sell_score = sell_score
        self._last_max_score = max_score
        
        # BUY signal: must meet threshold AND be higher than SELL
        if buy_score >= self.min_buy_score and buy_score > sell_score:
            # === BUY SIGNAL ===
            
            # Smart stop-loss placement
            if in_demand_zone:
                zone = next((z for z in demand_zones if z.zone_low <= current_price <= z.zone_high), None)
                if zone:
                    stop_loss = zone.zone_low * 0.995
                else:
                    stop_loss = current_price * 0.98
            elif nearest_hvn and current_price > nearest_hvn:
                stop_loss = nearest_hvn * 0.995
            else:
                stop_loss = current_price * 0.98
            
            # Smart take-profit
            if vp.poc > current_price:
                take_profit = vp.poc
            else:
                risk = current_price - stop_loss
                take_profit = current_price + (risk * 2)  # 2:1 R/R
            
            # Confidence score
            confidence = buy_score / max_score
            
            signal = Signal(
                strategy=self.name,
                symbol=symbol,
                side='BUY',
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=confidence,
                timestamp=datetime.now(),
                metadata={
                    'buy_score': buy_score,
                    'sell_score': sell_score,
                    'max_score': max_score,
                    'vp_position': vp_position,
                    'poc': vp.poc,
                    'val': vp.val,
                    'vah': vp.vah,
                    'imbalance': imbalance.volume_imbalance,
                    'cvd_divergence': cvd_divergence,
                    'in_demand_zone': in_demand_zone,
                    'liquidity': liquidity,
                    'spread': micro['spread_percent']
                }
            )
            
            if self.validate_signal(signal):
                return signal
        
        # SELL signal: must meet threshold AND be higher than BUY
        elif sell_score >= self.min_sell_score and sell_score > buy_score:
            # === SELL SIGNAL ===
            
            if in_supply_zone:
                zone = next((z for z in supply_zones if z.zone_low <= current_price <= z.zone_high), None)
                if zone:
                    stop_loss = zone.zone_high * 1.005
                else:
                    stop_loss = current_price * 1.02
            elif nearest_hvn and current_price < nearest_hvn:
                stop_loss = nearest_hvn * 1.005
            else:
                stop_loss = current_price * 1.02
            
            if vp.poc < current_price:
                take_profit = vp.poc
            else:
                risk = stop_loss - current_price
                take_profit = current_price - (risk * 2)
            
            signal = Signal(
                strategy=self.name,
                symbol=symbol,
                side='SELL',
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=sell_score / max_score,
                timestamp=datetime.now(),
                metadata={
                    'sell_score': sell_score,
                    'buy_score': buy_score,
                    'max_score': max_score,
                    'vp_position': vp_position,
                    'poc': vp.poc,
                    'val': vp.val,
                    'vah': vp.vah,
                    'imbalance': imbalance.volume_imbalance,
                    'cvd_divergence': cvd_divergence,
                    'in_supply_zone': in_supply_zone,
                    'liquidity': liquidity,
                    'spread': micro['spread_percent']
                }
            )
            
            if self.validate_signal(signal):
                return signal
        
        else:
            self.logger.info(f"No signal: scores below threshold ({self.min_score})")
            return None
