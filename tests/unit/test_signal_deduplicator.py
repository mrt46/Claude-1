"""
Unit tests for Signal Deduplicator.
"""

import time
from datetime import datetime, timedelta

import pytest

from src.execution.signal_deduplicator import SignalDeduplicator
from src.strategies.base import Signal


@pytest.fixture
def deduplicator():
    """Create signal deduplicator instance."""
    return SignalDeduplicator(
        cache_ttl_seconds=600,
        price_rounding_decimals=0
    )


@pytest.fixture
def deduplicator_short_ttl():
    """Create deduplicator with short TTL for testing."""
    return SignalDeduplicator(
        cache_ttl_seconds=1,  # 1 second for fast testing
        price_rounding_decimals=0
    )


@pytest.fixture
def sample_signal():
    """Create sample signal."""
    return Signal(
        strategy='InstitutionalStrategy',
        symbol='BTCUSDT',
        side='BUY',
        entry_price=42150.75,
        stop_loss=41890.25,
        take_profit=42670.00,
        confidence=0.78,
        timestamp=datetime(2025, 1, 28, 17, 3, 22),
        metadata={}
    )


class TestSignalDeduplicator:
    """Tests for SignalDeduplicator."""
    
    def test_init(self):
        """Test deduplicator initialization."""
        dedup = SignalDeduplicator(
            cache_ttl_seconds=600,
            price_rounding_decimals=0
        )
        
        assert dedup.cache_ttl == 600
        assert dedup.price_rounding == 0
        assert len(dedup.signal_cache) == 0
    
    def test_init_invalid_ttl(self):
        """Test initialization with invalid TTL."""
        with pytest.raises(ValueError, match="cache_ttl_seconds must be positive"):
            SignalDeduplicator(cache_ttl_seconds=-1)
    
    def test_init_invalid_rounding(self):
        """Test initialization with invalid rounding."""
        with pytest.raises(ValueError, match="price_rounding_decimals must be non-negative"):
            SignalDeduplicator(price_rounding_decimals=-1)
    
    def test_generate_signal_id(self, deduplicator, sample_signal):
        """Test signal ID generation."""
        signal_id = deduplicator.generate_signal_id(sample_signal)
        
        # Should round price and bucket time
        assert signal_id == 'BTCUSDT_BUY_42151_17:00'
        assert 'BTCUSDT' in signal_id
        assert 'BUY' in signal_id
        assert '42151' in signal_id  # Rounded from 42150.75
        assert '17:00' in signal_id  # Bucketed from 17:03
    
    def test_generate_signal_id_rounds_price(self, deduplicator):
        """Test price rounding in signal ID."""
        signal1 = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42150.75,
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime(2025, 1, 28, 17, 3, 22),
            metadata={}
        )
        
        signal2 = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42150.25,  # Different but rounds to same (42150)
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime(2025, 1, 28, 17, 4, 30),  # Same bucket
            metadata={}
        )
        
        id1 = deduplicator.generate_signal_id(signal1)
        id2 = deduplicator.generate_signal_id(signal2)
        
        # Should have same ID (rounded price and same time bucket)
        # 42150.75 rounds to 42151, 42150.25 rounds to 42150 - different!
        # Let's use prices that actually round to the same value
        signal3 = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42150.4,  # Rounds to 42150
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime(2025, 1, 28, 17, 4, 30),
            metadata={}
        )
        
        id3 = deduplicator.generate_signal_id(signal3)
        
        # signal1 (42150.75) rounds to 42151, signal3 (42150.4) rounds to 42150
        # They're different, so test with same rounded value
        signal4 = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42150.6,  # Also rounds to 42151
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime(2025, 1, 28, 17, 4, 30),
            metadata={}
        )
        
        id4 = deduplicator.generate_signal_id(signal4)
        
        # signal1 and signal4 should have same rounded price (both round to 42151)
        assert id1 == id4
    
    def test_generate_signal_id_time_bucket(self, deduplicator):
        """Test time bucket generation."""
        # Signals in same 5-minute bucket should have same ID
        signal1 = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42150.0,
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime(2025, 1, 28, 17, 3, 0),
            metadata={}
        )
        
        signal2 = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42150.0,
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime(2025, 1, 28, 17, 4, 59),  # Same bucket
            metadata={}
        )
        
        id1 = deduplicator.generate_signal_id(signal1)
        id2 = deduplicator.generate_signal_id(signal2)
        
        assert id1 == id2
        
        # Different bucket should have different ID
        signal3 = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42150.0,
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime(2025, 1, 28, 17, 6, 0),  # Different bucket
            metadata={}
        )
        
        id3 = deduplicator.generate_signal_id(signal3)
        assert id3 != id1
    
    def test_generate_signal_id_invalid_signal(self, deduplicator):
        """Test signal ID generation with invalid signal."""
        with pytest.raises(ValueError, match="Signal cannot be None"):
            deduplicator.generate_signal_id(None)
        
        # Missing symbol
        signal = Signal(
            strategy='Test',
            symbol='',  # Empty
            side='BUY',
            entry_price=42150.0,
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime.now(),
            metadata={}
        )
        with pytest.raises(ValueError, match="Signal must have symbol"):
            deduplicator.generate_signal_id(signal)
    
    def test_is_duplicate_detects_same_signal(self, deduplicator, sample_signal):
        """Test duplicate detection."""
        # First signal
        is_dup1 = deduplicator.is_duplicate(sample_signal)
        assert is_dup1 is False
        
        # Same signal again (duplicate!)
        is_dup2 = deduplicator.is_duplicate(sample_signal)
        assert is_dup2 is True
    
    def test_is_duplicate_different_signals(self, deduplicator):
        """Test different signals not flagged as duplicate."""
        signal1 = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime.now(),
            metadata={}
        )
        
        signal2 = Signal(
            strategy='Test',
            symbol='ETHUSDT',  # Different symbol
            side='BUY',
            entry_price=2200.0,
            stop_loss=2180.0,
            take_profit=2250.0,
            confidence=0.78,
            timestamp=datetime.now(),
            metadata={}
        )
        
        is_dup1 = deduplicator.is_duplicate(signal1)
        is_dup2 = deduplicator.is_duplicate(signal2)
        
        assert is_dup1 is False
        assert is_dup2 is False
    
    def test_is_duplicate_different_sides(self, deduplicator):
        """Test BUY and SELL signals are different."""
        signal1 = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime.now(),
            metadata={}
        )
        
        signal2 = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='SELL',  # Different side
            entry_price=42000.0,
            stop_loss=42100.0,
            take_profit=41500.0,
            confidence=0.78,
            timestamp=datetime.now(),
            metadata={}
        )
        
        is_dup1 = deduplicator.is_duplicate(signal1)
        is_dup2 = deduplicator.is_duplicate(signal2)
        
        assert is_dup1 is False
        assert is_dup2 is False
    
    def test_is_duplicate_expiry_cleanup(self, deduplicator_short_ttl):
        """Test expired entries are cleaned."""
        signal = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime.now(),
            metadata={}
        )
        
        # First signal
        is_dup1 = deduplicator_short_ttl.is_duplicate(signal)
        assert is_dup1 is False
        
        # Should be duplicate immediately
        is_dup2 = deduplicator_short_ttl.is_duplicate(signal)
        assert is_dup2 is True
        
        # Wait for expiry
        time.sleep(1.1)
        
        # Should not be duplicate after expiry
        is_dup3 = deduplicator_short_ttl.is_duplicate(signal)
        assert is_dup3 is False
    
    def test_register_execution(self, deduplicator, sample_signal):
        """Test registering signal execution."""
        # Register execution
        deduplicator.register_execution(sample_signal)
        
        # Should be in cache
        signal_id = deduplicator.generate_signal_id(sample_signal)
        assert signal_id in deduplicator.signal_cache
    
    def test_get_cache_stats(self, deduplicator, sample_signal):
        """Test cache statistics."""
        stats = deduplicator.get_cache_stats()
        
        assert 'cache_size' in stats
        assert 'cache_ttl_seconds' in stats
        assert stats['cache_size'] == 0
        assert stats['cache_ttl_seconds'] == 600
        
        # Add signal
        deduplicator.is_duplicate(sample_signal)
        
        stats = deduplicator.get_cache_stats()
        assert stats['cache_size'] == 1
    
    def test_clear_cache(self, deduplicator, sample_signal):
        """Test clearing cache."""
        # Add signal
        deduplicator.is_duplicate(sample_signal)
        assert len(deduplicator.signal_cache) == 1
        
        # Clear cache
        deduplicator.clear_cache()
        assert len(deduplicator.signal_cache) == 0
    
    def test_timezone_aware_timestamp(self, deduplicator):
        """Test handling timezone-aware timestamps."""
        from datetime import timezone
        
        signal = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42000.0,
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime(2025, 1, 28, 17, 3, 22, tzinfo=timezone.utc),
            metadata={}
        )
        
        # Should not raise error
        signal_id = deduplicator.generate_signal_id(signal)
        assert signal_id is not None
    
    def test_price_rounding_decimals(self):
        """Test different price rounding decimals."""
        dedup_0 = SignalDeduplicator(price_rounding_decimals=0)
        dedup_2 = SignalDeduplicator(price_rounding_decimals=2)
        
        signal = Signal(
            strategy='Test',
            symbol='BTCUSDT',
            side='BUY',
            entry_price=42150.756,
            stop_loss=41890.25,
            take_profit=42670.00,
            confidence=0.78,
            timestamp=datetime.now(),
            metadata={}
        )
        
        id_0 = dedup_0.generate_signal_id(signal)
        id_2 = dedup_2.generate_signal_id(signal)
        
        # Should round differently
        assert '42151' in id_0  # Rounded to nearest dollar
        assert '42150.76' in id_2  # Rounded to 2 decimals
