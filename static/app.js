"use strict";

const simulationButton = document.getElementById("simulate");

if (simulationButton) {
  simulationButton.addEventListener("click", async () => {
    const output = document.getElementById("simulation-result");
    simulationButton.disabled = true;
    output.textContent = "Running local simulation...";

    try {
      const response = await fetch(
        "/api/simulations/" + encodeURIComponent(simulationButton.dataset.caseId),
        { method: "POST" }
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Simulation failed.");
      }

      output.replaceChildren();
      const summary = document.createElement("p");
      summary.textContent = "HTTP " + data.http_status
        + " | Request ID " + data.request_id;
      output.appendChild(summary);

      const events = document.createElement("ul");
      for (const event of data.events) {
        const item = document.createElement("li");
        item.textContent = event.timestamp + " | " + event.service
          + " " + event.level + ": " + event.message
          + " [" + event.request_id + "]";
        events.appendChild(item);
      }
      output.appendChild(events);

      const note = document.createElement("p");
      note.textContent = data.note;
      output.appendChild(note);
    } catch (error) {
      output.textContent = "Could not run simulation: " + error.message;
    } finally {
      simulationButton.disabled = false;
    }
  });
}
