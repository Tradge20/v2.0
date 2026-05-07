const tableBody = document.querySelector("#inventoryTable tbody");
const resultBox = document.getElementById("result");

function addRow() {
  const row = document.createElement("tr");

  row.innerHTML = `
        <td>
            <select class="type">
                <option value="key">Key</option>
                <option value="core">Core</option>
            </select>
        </td>
        <td><input class="brand" required></td>
        <td><input class="number" required></td>
        <td>
          <div class="qty-control">
            <button type="button" class="qty-btn" onclick="changeQty(this, -1)">−</button>
            <input class="qty" type="number" inputmode="numeric" step="1" required value="0">
            <button type="button" class="qty-btn" onclick="changeQty(this, 1)">+</button>
          </div>
        </td>
        <td><button type="button" onclick="removeRow(this)">❌</button></td>
    `;

  tableBody.appendChild(row);
}

function removeRow(button) {
  button.closest("tr").remove();
}

function changeQty(button, delta) {
  const qtyInput = button.closest(".qty-control").querySelector(".qty");
  const currentValue = parseInt(qtyInput.value, 10);
  const safeValue = Number.isNaN(currentValue) ? 0 : currentValue;
  qtyInput.value = safeValue + delta;
}

document.getElementById("inventoryForm").addEventListener("submit", () => {
  const items = [];

  document.querySelectorAll("#inventoryTable tbody tr").forEach((row) => {
    items.push({
      type: row.querySelector(".type").value,
      brand: row.querySelector(".brand").value.trim(),
      number: row.querySelector(".number").value.trim(),
      quantity: parseInt(row.querySelector(".qty").value),
    });
  });

  document.getElementById("itemsField").value = JSON.stringify(items);
});

// Start with one row
addRow();
