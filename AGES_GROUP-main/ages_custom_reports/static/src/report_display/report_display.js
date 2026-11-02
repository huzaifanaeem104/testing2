/** @odoo-module **/

export function clipProjectName(name) {
    if (!name) {
        return "";
    }
    let text = String(name).trim();
    if (text.includes(" / ")) {
        const prefix = text.split(" / ", 1)[0];
        if (!prefix.includes("|")) {
            text = text.split(" / ").pop().trim();
        }
    }
    if (text.includes("|")) {
        text = text.split("|", 1)[0].trim();
    }
    const splitAt = text.indexOf(" - ");
    if (splitAt !== -1) {
        const left = text.slice(0, splitAt).trim();
        const right = text.slice(splitAt + 3).trim();
        if (left.toLowerCase() === right.toLowerCase()) {
            text = left;
        }
    }
    return text;
}
