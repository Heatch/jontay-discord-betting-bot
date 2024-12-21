from datetime import datetime

def odds(odds_string):
    """
    Parse a string of outcomes and probabilities and return a dictionary with odds info.
    
    Input format: "outcome1|prob1, outcome2|prob2, ..."
    Example: "charles wins|0.1, depp wins|0.32, sam wins|0.28, jessica wins|0.4"
    
    Returns: Dictionary with outcomes as keys, containing moneyline and decimal odds
    """
    try:
        # Split into individual outcome|probability pairs
        pairs = [pair.strip() for pair in odds_string.split(',')]
        
        # Dictionary to store results
        odds_info = {}
        
        # Process each outcome|probability pair
        for pair in pairs:
            outcome, prob = pair.split('|')
            outcome = outcome.strip()
            prob = float(prob)
            
            # Validate probability
            if not 0 < prob < 1:
                raise ValueError(f"Invalid probability {prob} for {outcome}. Must be between 0 and 1")
            
            # Calculate American moneyline
            if prob >= 0.5:
                moneyline = round(-100 * (prob / (1 - prob)))
            else:
                moneyline = round(100 * ((1 - prob) / prob))
                
            # Format moneyline string
            moneyline_str = f"+{moneyline}" if moneyline > 0 else str(moneyline)
            
            # Calculate decimal/European odds (multiplier)
            decimal_odds = round(1 / prob, 2)
            
            # Store in dictionary
            odds_info[outcome] = {
                'probability': prob,
                'moneyline': moneyline_str,
                'decimal_odds': decimal_odds
            }
            
        return odds_info
    
    except ValueError as e:
        raise ValueError(f"Error parsing odds string: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error parsing odds string: {e}")

def locktime (date_string):
    """
    Convert datetime string from "MM/DD/YYYY HH:MM" to "Month DDth, YYYY at H:MM AM/PM"
    """
    try:
        # Parse the input string
        dt = datetime.strptime(date_string, "%m/%d/%Y %H:%M")
        
        # Get month name
        month = dt.strftime("%B")
        
        # Get day with suffix (1st, 2nd, 3rd, 4th, etc.)
        day = dt.day
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        
        # Format time in 12-hour format with AM/PM
        time = dt.strftime("%I:%M %p").lstrip('0')  # lstrip('0') removes leading zero from hour
        
        # Combine everything
        return f"{month} {day}{suffix}, {dt.year} at {time}"
        
    except ValueError as e:
        raise ValueError(f"Invalid date format. Please use MM/DD/YYYY HH:MM (24-hour format). Error: {str(e)}")
    