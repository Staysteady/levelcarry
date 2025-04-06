from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, List, Tuple

@dataclass
class Position:
    near_date: datetime  # Near leg date
    far_date: datetime   # Far leg date
    lots: int           # positive for long, negative for short
    daily_rate: Optional[float] = None
    
    @property
    def is_long(self) -> bool:
        return self.lots > 0
    
    @property
    def is_short(self) -> bool:
        return self.lots < 0
    
    @property
    def duration_days(self) -> int:
        """Calculate the number of days in the carry."""
        return (self.far_date - self.near_date).days
    
    def get_value(self) -> float:
        """Calculate the total value of the position."""
        if not self.daily_rate:
            return 0.0
        return abs(self.lots) * self.duration_days * self.daily_rate
    
    def overlaps_with(self, other: 'Position') -> bool:
        """Check if this position overlaps in time with another position."""
        return (
            (self.near_date <= other.far_date and self.far_date >= other.near_date) or
            (other.near_date <= self.far_date and other.far_date >= self.near_date)
        )
    
    def get_overlap_period(self, other: 'Position') -> Optional[Tuple[datetime, datetime]]:
        """Get the overlapping period between two positions, if any."""
        if not self.overlaps_with(other):
            return None
        
        overlap_start = max(self.near_date, other.near_date)
        overlap_end = min(self.far_date, other.far_date)
        return (overlap_start, overlap_end)

@dataclass
class TradingCard:
    owner: str
    positions: List[Position]
    
    def get_net_position(self) -> int:
        """Calculate net position across all trades."""
        return sum(pos.lots for pos in self.positions)
    
    def get_positions_in_range(self, start_date: datetime, end_date: datetime) -> List[Position]:
        """Get all positions within a date range."""
        return [
            pos for pos in self.positions
            if (start_date <= pos.near_date <= end_date or 
                start_date <= pos.far_date <= end_date)
        ]
    
    def find_matching_positions(self, other_card: 'TradingCard', tolerance: float = 0.1) -> List[Tuple[Position, Position, float]]:
        """Find matching positions between two cards for potential tidies.
        Returns list of tuples: (position1, position2, payment_needed)
        where payment_needed is the amount one side needs to pay to level the carry.
        """
        matches = []
        
        for pos1 in self.positions:
            for pos2 in other_card.positions:
                # Skip if same direction
                if (pos1.is_long and pos2.is_long) or (pos1.is_short and pos2.is_short):
                    continue
                
                # First priority: Level carries (exact matches)
                if (pos1.near_date == pos2.near_date and 
                    pos1.far_date == pos2.far_date and 
                    abs(pos1.lots) == abs(pos2.lots)):
                    matches.append((pos1, pos2, 0.0))  # Zero payment needed
                    continue
                
                # Second priority: Overlapping periods with similar values
                overlap = pos1.get_overlap_period(pos2)
                if overlap:
                    # Calculate values for the overlap period
                    overlap_days = (overlap[1] - overlap[0]).days
                    min_lots = min(abs(pos1.lots), abs(pos2.lots))
                    
                    if pos1.daily_rate and pos2.daily_rate:
                        val1 = min_lots * overlap_days * pos1.daily_rate
                        val2 = min_lots * overlap_days * pos2.daily_rate
                        
                        # Check if values are within tolerance
                        if val1 > 0 and val2 > 0:
                            max_val = max(val1, val2)
                            diff = abs(val1 - val2)
                            if diff / max_val <= tolerance:
                                # Calculate payment needed to level the carry
                                payment = diff / 2  # Split the difference
                                matches.append((pos1, pos2, payment))
        
        # Sort matches: level carries first, then by payment size
        matches.sort(key=lambda x: x[2])  # Sort by payment amount
        return matches 