package com.bsch.clinics;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.text.InputType;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;

public class MainActivity extends Activity {
    private WebView web;
    private SharedPreferences prefs;
    private static final String PREFS = "bsch_clinics";
    private static final String URL_KEY = "server_url";

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setUserAgentString(s.getUserAgentString()+" BSCHClinicsAndroid/1.1");
        web.setWebViewClient(new WebViewClient());
        setContentView(web);
        String saved = prefs.getString(URL_KEY, "");
        if (saved == null || saved.trim().isEmpty()) showServerDialog();
        else web.loadUrl(saved);
    }

    private void showServerDialog() {
        final EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setHint("http://192.168.1.10:4173/");
        input.setText(getString(com.bsch.clinics.R.string.server_url));
        new AlertDialog.Builder(this)
            .setTitle("إعداد خادم المستشفى")
            .setMessage("اكتب عنوان الخادم الداخلي، مثال: http://192.168.1.10:4173/")
            .setView(input)
            .setCancelable(false)
            .setPositiveButton("حفظ وفتح", (dialog, which) -> {
                String url = input.getText().toString().trim();
                if (!url.endsWith("/")) url += "/";
                prefs.edit().putString(URL_KEY, url).apply();
                web.loadUrl(url);
            })
            .setNegativeButton("استخدام العنوان الافتراضي", (dialog, which) -> {
                String url = getString(com.bsch.clinics.R.string.server_url);
                prefs.edit().putString(URL_KEY, url).apply();
                web.loadUrl(url);
            }).show();
    }

    @Override public void onBackPressed() { if (web.canGoBack()) web.goBack(); else super.onBackPressed(); }
}
