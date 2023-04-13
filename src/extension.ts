import { execFileSync } from "child_process";
import * as vscode from "vscode";

export function activate(context: vscode.ExtensionContext) {
  vscode.languages.registerDocumentRangeFormattingEditProvider("scheme", {
    provideDocumentRangeFormattingEdits: (document, range) => {
      try {
        const formattedText = execFileSync(
          vscode.workspace.getConfiguration("scheme-fmt").pythonPath,
          [context.asAbsolutePath("scheme-fmt.py"), "-"],
          { input: document.getText(range) }
        );
        return [vscode.TextEdit.replace(range, formattedText.toString())];
      } catch (e) {
        vscode.window.showErrorMessage(`scheme-fmt failed: ${e}`);
      }
    },
  });
}
