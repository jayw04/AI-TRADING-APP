"""Background services: scheduled jobs and pollers that bring broker state into
the application. None of these accept user input; they read from Alpaca and
either persist to the DB or publish to the event bus.
"""
