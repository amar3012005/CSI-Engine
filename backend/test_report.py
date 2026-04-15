import sys
from app.api.report import generate_report
from flask import Flask, request, jsonify
from app.services.report_agent import ReportAgent

agent = ReportAgent(graph_id="", simulation_id="sim_4bc880be653c", simulation_requirement="Find me the exact reason for the death of Nile River")
print("Agent created successfully.")
try:
    agent.generate_report()
except Exception as e:
    import traceback
    print("Error generating:")
    traceback.print_exc()

