(() => {
    "use strict";

    const collator = new Intl.Collator("pt-BR", {
        numeric: true,
        sensitivity: "base"
    });

    function normalizeText(value) {
        return String(value ?? "").replace(/\s+/g, " ").trim();
    }

    function parseSortable(value) {
        const text = normalizeText(value);

        if (!text || text === "-") {
            return { type: "empty", value: null };
        }

        let match = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
        if (match) {
            return {
                type: "number",
                value: Number(`${match[3]}${match[2]}${match[1]}`)
            };
        }

        match = text.match(/^(\d{2})\/(\d{4})$/);
        if (match) {
            return {
                type: "number",
                value: Number(`${match[2]}${match[1]}`)
            };
        }

        match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (match) {
            return {
                type: "number",
                value: Number(`${match[1]}${match[2]}${match[3]}`)
            };
        }

        if (
            /^R\$\s*/i.test(text) ||
            /%$/.test(text) ||
            /^-?[\d.]+,\d+$/.test(text) ||
            /^-?\d+$/.test(text)
        ) {
            const numericText = text
                .replace(/R\$/gi, "")
                .replace(/%/g, "")
                .replace(/\s/g, "")
                .replace(/\./g, "")
                .replace(",", ".");

            const number = Number(numericText);

            if (Number.isFinite(number)) {
                return { type: "number", value: number };
            }
        }

        return {
            type: "text",
            value: text.toLocaleLowerCase("pt-BR")
        };
    }

    function compareValues(a, b, direction) {
        if (a.type === "empty" && b.type === "empty") return 0;
        if (a.type === "empty") return 1;
        if (b.type === "empty") return -1;

        let result;

        if (a.type === "number" && b.type === "number") {
            result = a.value - b.value;
        } else {
            result = collator.compare(String(a.value), String(b.value));
        }

        return result * direction;
    }

    function makeSortable(table) {
        if (table.dataset.sortInitialized === "true") return;
        if (table.dataset.sortable === "false") return;

        if (table.querySelector("tbody input, tbody select, tbody textarea")) {
            return;
        }

        const tbody = table.tBodies[0];
        const headerRow = table.tHead?.rows?.[0];

        if (!tbody || !headerRow || tbody.rows.length < 2) {
            return;
        }

        table.dataset.sortInitialized = "true";

        [...headerRow.cells].forEach((th, columnIndex) => {
            const label = normalizeText(th.textContent);

            if (!label || th.dataset.noSort === "true") return;

            th.classList.add("sortable-header");
            th.tabIndex = 0;
            th.setAttribute("role", "button");
            th.setAttribute("aria-sort", "none");
            th.title = `Ordenar por ${label}`;

            const sortColumn = () => {
                const nextDirection =
                    th.dataset.sortDirection === "asc" ? "desc" : "asc";
                const direction = nextDirection === "asc" ? 1 : -1;

                [...headerRow.cells].forEach(other => {
                    if (other !== th) {
                        other.dataset.sortDirection = "";
                        other.setAttribute("aria-sort", "none");
                    }
                });

                const rows = [...tbody.rows].map((row, index) => ({
                    row,
                    index,
                    parsed: parseSortable(
                        row.cells[columnIndex]?.dataset.sortValue ??
                        row.cells[columnIndex]?.innerText ??
                        ""
                    )
                }));

                rows.sort((left, right) => {
                    const result = compareValues(
                        left.parsed,
                        right.parsed,
                        direction
                    );
                    return result || (left.index - right.index);
                });

                rows.forEach(item => tbody.appendChild(item.row));

                th.dataset.sortDirection = nextDirection;
                th.setAttribute(
                    "aria-sort",
                    nextDirection === "asc" ? "ascending" : "descending"
                );
            };

            th.addEventListener("click", sortColumn);
            th.addEventListener("keydown", event => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    sortColumn();
                }
            });
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        document
            .querySelectorAll(
                'table[data-sortable="true"], .table-responsive table:not([data-sortable="false"])'
            )
            .forEach(makeSortable);
    });
})();
