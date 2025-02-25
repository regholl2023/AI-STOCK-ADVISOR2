from openai import OpenAI
import time
from datetime import datetime
import json
import re
from config import *
from log import *
from robinhood import *
from trading_logs import *


# Initialize session and login
openai_client = OpenAI(api_key=OPENAI_API_KEY)


# Make AI request to OpenAI API
def make_ai_request(prompt):
    ai_resp = openai_client.chat.completions.create(
        model=OPENAI_MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    return ai_resp


# Parse AI response
def parse_ai_response(ai_response):
    try:
        ai_content = re.sub(r'```json|```', '', ai_response.choices[0].message.content.strip())
        decisions = json.loads(ai_content)
    except json.JSONDecodeError as e:
        raise Exception("Invalid JSON response from OpenAI: " + ai_response.choices[0].message.content.strip())
    return decisions


# Get AI amount guidelines
def get_ai_amount_guidelines():
    sell_guidelines = []
    if MIN_SELLING_AMOUNT_USD is not False:
        sell_guidelines.append(f"Minimum {MIN_SELLING_AMOUNT_USD} USD")
    if MAX_SELLING_AMOUNT_USD is not False:
        sell_guidelines.append(f"Maximum {MAX_SELLING_AMOUNT_USD} USD")
    sell_guidelines = ", ".join(sell_guidelines) if sell_guidelines else None

    buy_guidelines = []
    if MIN_BUYING_AMOUNT_USD is not False:
        buy_guidelines.append(f"Minimum {MIN_BUYING_AMOUNT_USD} USD")
    if MAX_BUYING_AMOUNT_USD is not False:
        buy_guidelines.append(f"Maximum {MAX_BUYING_AMOUNT_USD} USD")
    buy_guidelines = ", ".join(buy_guidelines) if buy_guidelines else None

    return sell_guidelines, buy_guidelines


# Make AI-based decisions on stock portfolio and watchlist
def make_ai_decisions(buying_power, portfolio_overview, watchlist_overview):
    sell_guidelines, buy_guidelines = get_ai_amount_guidelines()
    symbols_under_limit = get_stocks_from_db_under_day_trade_limit() if PDT_PROTECTION else []

    constraints = [
        f"- Maintain a portfolio size of fewer than {PORTFOLIO_LIMIT} stocks.",
        f"- Total Buying Power: {buying_power} USD initially."
    ]
    if sell_guidelines:
        constraints.append(f"- Sell Amounts Guidelines: {sell_guidelines}")
    if buy_guidelines:
        constraints.append(f"- Buy Amounts Guidelines: {buy_guidelines}")
    if len(symbols_under_limit) > 0:
        constraints.append(f"- Stocks under PDT Limit: {', '.join(symbols_under_limit)}")
    if len(TRADE_EXCEPTIONS) > 0:
        constraints.append(f"- Trade Exceptions (exclude from trading in any decisions): {', '.join(TRADE_EXCEPTIONS)}")

    ai_prompt = (
        "**Decision-Making AI Prompt:**\n\n"
        "**Context:**\n"
        f"You are an investment advisor managing a stock portfolio and watchlist. Every {RUN_INTERVAL_SECONDS} seconds, you analyze market conditions to make informed investment decisions.{chr(10)}{chr(10)}"
        "**Task:**\n"
        "Analyze the provided portfolio and watchlist data to recommend:\n"
        "1. Stocks to sell, prioritizing those that maximize buying power and profit potential.\n"
        "2. Stocks to buy that align with available funds and current market conditions.\n\n"
        "**Constraints:**\n"
        f"{chr(10).join(constraints)}"
        "\n\n"
        "**Portfolio Overview:**\n"
        "```json\n"
        f"{json.dumps(portfolio_overview, indent=1)}{chr(10)}"
        "```\n\n"
        "**Watchlist Overview:**\n"
        "```json\n"
        f"{json.dumps(watchlist_overview, indent=1)}{chr(10)}"
        "```\n\n"
        "**Response Format:**\n"
        "Return your decisions in a JSON array with this structure:\n"
        "```json\n"
        "[\n"
        '  {"symbol": "<symbol>", "decision": "<decision>", "quantity": <quantity>},\n'
        "  ...\n"
        "]\n"
        "```\n"
        "- `symbol`: Stock ticker symbol.\n"
        "- `decision`: One of `buy`, `sell`, or `hold`.\n"
        "- `quantity`: Recommended transaction quantity.\n\n"
        "**Instructions:**\n"
        "- Provide only the JSON output with no additional text.\n"
        "- Return an empty array if no actions are necessary."
    )
    log_debug(f"AI making-decisions prompt:{chr(10)}{ai_prompt}")
    ai_response = make_ai_request(ai_prompt)
    log_debug(f"AI making-decisions response:{chr(10)}{ai_response.choices[0].message.content.strip()}")
    decisions = parse_ai_response(ai_response)
    return decisions


# Make post-decisions adjustment based on trading results
def make_ai_post_decisions_adjustment(buying_power, trading_results):
    sell_guidelines, buy_guidelines = get_ai_amount_guidelines()
    symbols_under_limit = get_stocks_from_db_under_day_trade_limit() if PDT_PROTECTION else []

    constraints = [
        f"- Maintain a portfolio size of fewer than {PORTFOLIO_LIMIT} stocks.",
        f"- Total Buying Power: {buying_power} USD initially."
    ]
    if sell_guidelines:
        constraints.append(f"- Sell Amounts Guidelines: {sell_guidelines}")
    if buy_guidelines:
        constraints.append(f"- Buy Amounts Guidelines: {buy_guidelines}")
    if len(symbols_under_limit) > 0:
        constraints.append(f"- Stocks under PDT Limit: {', '.join(symbols_under_limit)}")
    if len(TRADE_EXCEPTIONS) > 0:
        constraints.append(f"- Trade Exceptions (exclude from trading in any decisions): {', '.join(TRADE_EXCEPTIONS)}")

    ai_prompt = (
        "**Post-Decision Adjustments AI Prompt:**\n\n"
        "**Context:**\n"
        "You are an investment advisor tasked with reviewing and adjusting prior trading decisions. Your goal is to optimize buying power and profit potential by analyzing trading results and making necessary changes.\n\n"
        "**Task:**\n"
        "1. Review previous trading outcomes and resolve any errors.\n"
        "2. Reorder and adjust sell decisions to enhance buying power.\n"
        "3. Update buy recommendations based on the newly available buying power.\n\n"
        "**Constraints:**\n"
        f"{chr(10).join(constraints)}"
        "\n\n"
        "**Trading Results:**\n"
        "```json\n"
        f"{json.dumps(trading_results, indent=1)}{chr(10)}"
        "```\n\n"
        "**Response Format:**\n"
        "Return your decisions in a JSON array with this structure:\n"
        "```json\n"
        "[\n"
        '  {"symbol": "<symbol>", "decision": "<decision>", "quantity": <quantity>},\n'
        "  ...\n"
        "]\n"
        "```\n"
        "- `symbol`: Stock ticker symbol.\n"
        "- `decision`: One of `buy`, `sell`, or `hold`.\n"
        "- `quantity`: Recommended transaction quantity.\n\n"
        "**Instructions:**\n"
        "- Provide only the JSON output with no additional text.\n"
        "- Return an empty array if no actions are necessary."
    )
    log_debug(f"AI post-decisions-adjustment prompt:{chr(10)}{ai_prompt}")
    ai_response = make_ai_request(ai_prompt)
    log_debug(f"AI post-decisions-adjustment response:{chr(10)}{ai_response.choices[0].message.content.strip()}")
    decisions = parse_ai_response(ai_response)
    return decisions


# Limit watchlist stocks based on the current week number
def limit_watchlist_stocks(watchlist_stocks, limit):
    if len(watchlist_stocks) <= limit:
        return watchlist_stocks

    # Sort watchlist stocks by symbol
    watchlist_stocks = sorted(watchlist_stocks, key=lambda x: x['symbol'])

    # Get the current month number
    current_month = datetime.now().month

    # Calculate the number of parts
    num_parts = (len(watchlist_stocks) + limit - 1) // limit  # Ceiling division

    # Determine the part to return based on the current month number
    part_index = (current_month - 1) % num_parts
    start_index = part_index * limit
    end_index = min(start_index + limit, len(watchlist_stocks))

    return watchlist_stocks[start_index:end_index]


# Main trading bot function
def trading_bot():
    log_info("Getting portfolio stocks...")
    portfolio_stocks = get_portfolio_stocks()

    log_debug(f"Portfolio stocks total: {len(portfolio_stocks)}")

    portfolio_stocks_value = 0
    for stock in portfolio_stocks.values():
        portfolio_stocks_value += float(stock['price']) * float(stock['quantity'])
    portfolio = [f"{symbol} ({round(float(stock['price']) * float(stock['quantity']) / portfolio_stocks_value * 100, 2)}%)" for symbol, stock in portfolio_stocks.items()]
    log_info(f"Portfolio stocks to proceed: {'None' if len(portfolio) == 0 else ', '.join(portfolio)}")

    log_info("Prepare portfolio stocks for AI analysis...")
    portfolio_overview = {}
    for symbol, stock_data in portfolio_stocks.items():
        portfolio_overview[symbol] = extract_my_stocks_data(stock_data)
        portfolio_overview[symbol] = enrich_with_moving_averages(portfolio_overview[symbol], symbol)
        portfolio_overview[symbol] = enrich_with_analyst_ratings(portfolio_overview[symbol], symbol)

    log_info("Getting watchlist stocks...")
    watchlist_stocks = []
    for watchlist_name in WATCHLIST_NAMES:
        try:
            watchlist_stocks.extend(get_watchlist_stocks(watchlist_name))
            watchlist_stocks = [dict(t) for t in {tuple(d.items()) for d in watchlist_stocks}]
        except Exception as e:
            log_error(f"Error getting watchlist stocks for {watchlist_name}: {e}")

    log_debug(f"Watchlist stocks total: {len(watchlist_stocks)}")

    watchlist_overview = {}
    if len(watchlist_stocks) > 0:
        log_debug(f"Limiting watchlist stocks to overview limit of {WATCHLIST_OVERVIEW_LIMIT}...")
        watchlist_stocks = limit_watchlist_stocks(watchlist_stocks, WATCHLIST_OVERVIEW_LIMIT)

        log_debug(f"Removing portfolio stocks from watchlist...")
        watchlist_stocks = [stock for stock in watchlist_stocks if stock['symbol'] not in portfolio_stocks.keys()]

        log_info(f"Watchlist stocks to proceed: {', '.join([stock['symbol'] for stock in watchlist_stocks])}")

        log_info("Prepare watchlist overview for AI analysis...")
        for stock_data in watchlist_stocks:
            symbol = stock_data['symbol']
            watchlist_overview[symbol] = extract_watchlist_data(stock_data)
            watchlist_overview[symbol] = enrich_with_moving_averages(watchlist_overview[symbol], symbol)
            watchlist_overview[symbol] = enrich_with_analyst_ratings(watchlist_overview[symbol], symbol)

    if len(portfolio_overview) == 0 and len(watchlist_overview) == 0:
        log_warning("No stocks to analyze, skipping AI-based decision-making...")
        return {}

    decisions_data = []
    trading_results = {}
    post_decisions_adjustment_count = 0

    try:
        log_info("Making AI-based decision...")
        buying_power = get_buying_power()
        decisions_data = make_ai_decisions(buying_power, portfolio_overview, watchlist_overview)
    except Exception as e:
        log_error(f"Error making AI-based decision: {e}")


    while len(decisions_data) > 0:
        log_debug(f"Total decisions: {len(decisions_data)}")
        log_debug(f"Decisions:{chr(10)}{json.dumps(decisions_data, indent=1)}")

        log_info("Executing decisions...")
        for decision_data in decisions_data:
            symbol = decision_data['symbol']
            decision = decision_data['decision']
            quantity = decision_data['quantity']
            log_info(f"{symbol} > Decision: {decision} of {quantity}")

            if symbol in TRADE_EXCEPTIONS:
                trading_results[symbol] = {"symbol": symbol, "quantity": quantity, "decision": decision, "result": "error", "details": "Trade exception"}
                log_warning(f"{symbol} > Decision skipped due to trade exception")
                continue

            if decision == "sell":
                try:
                    sell_resp = sell_stock(symbol, quantity)
                    if sell_resp and 'id' in sell_resp:
                        if sell_resp['id'] == "demo":
                            trading_results[symbol] = {"symbol": symbol, "quantity": quantity, "decision": "sell", "result": "success", "details": "Demo mode"}
                            log_info(f"{symbol} > Demo > Sold {quantity} stocks")
                        elif sell_resp['id'] == "cancelled":
                            trading_results[symbol] = {"symbol": symbol, "quantity": quantity, "decision": "sell", "result": "cancelled", "details": "Cancelled by user"}
                            log_info(f"{symbol} > Sell cancelled by user")
                        else:
                            details = extract_sell_response_data(sell_resp)
                            trading_results[symbol] = {"symbol": symbol, "quantity": quantity, "decision": "sell", "result": "success", "details": details}
                            log_trade_to_db(symbol, "sell", quantity)
                            log_info(f"{symbol} > Sold {quantity} stocks")
                    else:
                        details = sell_resp['detail'] if 'detail' in sell_resp else sell_resp
                        trading_results[symbol] = {"symbol": symbol, "quantity": quantity, "decision": "sell", "result": "error", "details": details}
                        log_error(f"{symbol} > Error selling: {details}")
                except Exception as e:
                    trading_results[symbol] = {"symbol": symbol, "quantity": quantity, "decision": "sell", "result": "error", "details": str(e)}
                    log_error(f"{symbol} > Error selling: {e}")

            if decision == "buy":
                try:
                    buy_resp = buy_stock(symbol, quantity)
                    if buy_resp and 'id' in buy_resp:
                        if buy_resp['id'] == "demo":
                            trading_results[symbol] = {"symbol": symbol, "quantity": quantity, "decision": "buy", "result": "success", "details": "Demo mode"}
                            log_info(f"{symbol} > Demo > Bought {quantity} stocks")
                        elif buy_resp['id'] == "cancelled":
                            trading_results[symbol] = {"symbol": symbol, "quantity": quantity, "decision": "buy", "result": "cancelled", "details": "Cancelled by user"}
                            log_info(f"{symbol} > Buy cancelled by user")
                        else:
                            details = extract_buy_response_data(buy_resp)
                            trading_results[symbol] = {"symbol": symbol, "quantity": quantity, "decision": "buy", "result": "success", "details": details}
                            log_trade_to_db(symbol, "buy", quantity)
                            log_info(f"{symbol} > Bought {quantity} stocks")
                    else:
                        details = buy_resp['detail'] if 'detail' in buy_resp else buy_resp
                        trading_results[symbol] = {"symbol": symbol, "quantity": quantity, "decision": "buy", "result": "error", "details": details}
                        log_error(f"{symbol} > Error buying: {details}")
                except Exception as e:
                    trading_results[symbol] = {"symbol": symbol, "quantity": quantity, "decision": "buy", "result": "error", "details": str(e)}
                    log_error(f"{symbol} > Error buying: {e}")

        if (MAX_POST_DECISIONS_ADJUSTMENTS is False
                or post_decisions_adjustment_count >= MAX_POST_DECISIONS_ADJUSTMENTS):
            break

        try:
            post_decisions_adjustment_count += 1
            log_info(f"Making AI-based post-decision analysis, attempt: {post_decisions_adjustment_count}/{MAX_POST_DECISIONS_ADJUSTMENTS}...")
            buying_power = get_buying_power()
            decisions_data = make_ai_post_decisions_adjustment(buying_power, trading_results)
            log_debug(f"Total post-decision adjustments: {len(decisions_data)}")
        except Exception as e:
            log_error(f"Error making post-decision analysis: {e}")
            break

    return trading_results


# Run trading bot in a loop
def main():
    while True:
        try:
            if is_market_open():
                run_interval_seconds = RUN_INTERVAL_SECONDS
                log_info(f"Market is open, running trading bot in {MODE} mode...")

                trading_results = trading_bot()

                sold_stocks = [f"{result['symbol']} ({result['quantity']})" for result in trading_results.values() if result['decision'] == "sell" and result['result'] == "success"]
                bought_stocks = [f"{result['symbol']} ({result['quantity']})" for result in trading_results.values() if result['decision'] == "buy" and result['result'] == "success"]
                errors = [f"{result['symbol']} ({result['details']})" for result in trading_results.values() if result['result'] == "error"]
                log_info(f"Sold: {'None' if len(sold_stocks) == 0 else ', '.join(sold_stocks)}")
                log_info(f"Bought: {'None' if len(bought_stocks) == 0 else ', '.join(bought_stocks)}")
                log_info(f"Errors: {'None' if len(errors) == 0 else ', '.join(errors)}")
            else:
                run_interval_seconds = 60
                log_info("Market is closed, waiting for next run...")
        except Exception as e:
            run_interval_seconds = 60
            log_error(f"Trading bot error: {e}")

        log_info(f"Waiting for {run_interval_seconds} seconds...")
        time.sleep(run_interval_seconds)


# Run the main function
if __name__ == '__main__':
    confirm = input(f"Are you sure you want to run the bot in {MODE} mode? (yes/no): ")
    if confirm.lower() != "yes":
        log_warning("Exiting the bot...")
        exit()
    main()
