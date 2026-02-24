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
        <td><input class="qty" type="number" required></td>
        <td><button type="button" onclick="removeRow(this)">❌</button></td>
    `;

  tableBody.appendChild(row);
}

function removeRow(button) {
  button.closest("tr").remove();
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
