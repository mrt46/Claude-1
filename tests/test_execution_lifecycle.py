"""
Tests for order lifecycle management.
"""

from datetime import datetime

import pytest

from src.execution.lifecycle import OrderLifecycleManager, OrderStatus


class TestOrderLifecycleManager:
    """Tests for OrderLifecycleManager."""
    
    def test_create_order(self):
        """Test creating order."""
        manager = OrderLifecycleManager()
        
        order = manager.create_order(
            symbol='BTCUSDT',
            side='BUY',
            order_type='market',
            quantity=0.1,
            price=None
        )
        
        assert order.id is not None
        assert order.symbol == 'BTCUSDT'
        assert order.side == 'BUY'
        assert order.order_type == 'market'
        assert order.quantity == 0.1
        assert order.status == OrderStatus.PENDING
        assert order.created_at is not None
    
    def test_update_order_status(self):
        """Test updating order status."""
        manager = OrderLifecycleManager()
        
        order = manager.create_order('BTCUSDT', 'BUY', 'market', 0.1)
        order_id = order.id
        
        manager.update_order_status(order_id, OrderStatus.SUBMITTED, exchange_order_id='12345')
        
        updated_order = manager.get_order(order_id)
        assert updated_order.status == OrderStatus.SUBMITTED
        assert updated_order.exchange_order_id == '12345'
        assert updated_order.submitted_at is not None
    
    def test_update_order_filled(self):
        """Test updating order to filled."""
        manager = OrderLifecycleManager()
        
        order = manager.create_order('BTCUSDT', 'BUY', 'market', 0.1)
        order_id = order.id
        
        manager.update_order_status(
            order_id,
            OrderStatus.FILLED,
            filled_quantity=0.1,
            avg_fill_price=42000.0
        )
        
        updated_order = manager.get_order(order_id)
        assert updated_order.status == OrderStatus.FILLED
        assert updated_order.filled_quantity == 0.1
        assert updated_order.avg_fill_price == 42000.0
        assert updated_order.filled_at is not None
    
    def test_get_order(self):
        """Test getting order by ID."""
        manager = OrderLifecycleManager()
        
        order = manager.create_order('BTCUSDT', 'BUY', 'market', 0.1)
        retrieved = manager.get_order(order.id)
        
        assert retrieved is not None
        assert retrieved.id == order.id
    
    def test_get_open_orders(self):
        """Test getting open orders."""
        manager = OrderLifecycleManager()
        
        # Create multiple orders
        order1 = manager.create_order('BTCUSDT', 'BUY', 'market', 0.1)
        order2 = manager.create_order('ETHUSDT', 'SELL', 'limit', 1.0, price=3000.0)
        
        # Fill one
        manager.update_order_status(order1.id, OrderStatus.FILLED)
        
        open_orders = manager.get_open_orders()
        
        assert len(open_orders) == 1
        assert open_orders[0].id == order2.id
    
    @pytest.mark.asyncio
    async def test_monitor_order(self):
        """Test monitoring order."""
        manager = OrderLifecycleManager(market_order_timeout=5)
        
        order = manager.create_order('BTCUSDT', 'BUY', 'market', 0.1)
        order_id = order.id
        
        # Mock callback that returns FILLED immediately
        async def check_status(order_id):
            return OrderStatus.FILLED
        
        # Monitor should complete quickly
        await manager.monitor_order(order_id, check_status)
        
        # Order should be marked as filled
        updated_order = manager.get_order(order_id)
        assert updated_order.status == OrderStatus.FILLED
