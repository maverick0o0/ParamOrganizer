# ParamOrganizer

Ever feel lost in a sea of HTTP params and waste time digging through old requests to find the one you need?  
Or when you’re doing an IDOR test, you keep flipping back just to grab that one parameter?  
Even with mass‑assignment checks, testing each param one by one can take forever.

**Meet your new best friend**: with one click, this tool grabs every request and response param, lines them up in a clear table, and keeps them right there for you.

**ParamOrganizer** is a Burp Suite extension (written in Jython) that flattens and displays HTTP request/response parameters in a table. It supports:

- Drag-and-drop table reordering  
- Context-menu actions (show in message, delete entries)  
- Keyboard shortcut (DEL) to delete  
- Import/export table data as JSON  
- Custom parameter addition  

---

## 📦 Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/<your-username>/ParamOrganizer.git
   ```

2. In Burp Suite:
   - Go to **Extender → Extensions → Add**
   - Select **Python** as the extension type
   - Load `src/simple.py`

---

## ▶️ How It Works

Right‑click on any request or response in Burp → **ParamOrganizer** → *Just Request / Just Response / Request with Response*.

Select your **unique key** when prompted (or choose Custom to type one in).

A new tab opens showing a table of parameter names and values from that message.

---

## 🔑 Key Features

### 🔁 Automatic JSON Flattening

Deeply nested JSON objects and arrays are flattened into simple key–value pairs.

**Example**:
```json
{
  "user": {
    "id": 42,
    "profile": { "email": "a@b.com" }
  }
}
```

**Becomes**:

| Parameter            | Value     |
|----------------------|-----------|
| user.id              | 42        |
| user.profile.email   | a@b.com   |

---

### 🖱️ Interactive Swing Table

- **Drag & Drop**: Reorder rows freely  
- **Keyboard Shortcut**: Select and press `DEL` to remove  
- **Context Menu Actions**:
  - *Show in Message*: Highlights the parameter in the original message  
  - *Delete Entry(s)*: Instantly removes selected row(s)  

---

### 🧬 Unique-Key Grouping

Choose a parameter (e.g. `email` or `id`) as a “unique key.”  
This names the tab (e.g. `email:user@example.com`), and updates it if the same key/value is reloaded.

---

### ✍️ Custom Entry Support

Manually add key/value pairs—even if not in the HTTP data.  
These persist through tab updates.

---

### 📤 Import / Export JSON

- **Export**: Saves your table as a JSON array:
  ```json
  [
    { "Parameter": "email", "Value": "user@example.com", "Source": "req" },
    { "Parameter": "status", "Value": "active",         "Source": "resp" }
  ]
  ```
- **Import**: Loads a saved JSON file, clearing and rebuilding the table (custom entries included).

---

### 📋 Copy to Clipboard

Two buttons allow instant copying of all parameter names or values.

---

### 👀 View Toggles

- **Show Full Path**: e.g. `data.user.id` vs just `id`
- **Hide Source Suffix**: Optional removal of `(req)/(resp)` tags

---

## 📸 Screenshots & Demo

> ![Demo of ParamOrganizer](media/demo.gif)

---

## 📝 License

This project is licensed under the [MIT License](LICENSE).

