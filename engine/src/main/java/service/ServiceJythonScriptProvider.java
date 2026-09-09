package service;

import ghidra.jython.JythonScriptProvider;
import ghidra.util.classfinder.ExtensionPointProperties;

/** Preserve the legacy untagged .py runtime while still honoring explicit @runtime tags. */
@ExtensionPointProperties(priority = 100)
public class ServiceJythonScriptProvider extends JythonScriptProvider {}
