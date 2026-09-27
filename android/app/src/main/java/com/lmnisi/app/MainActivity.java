package com.lmnisi.app;
import android.app.*;import android.os.*;import android.webkit.*;
public class MainActivity extends Activity{
 public void onCreate(Bundle b){super.onCreate(b);WebView w=new WebView(this);w.getSettings().setJavaScriptEnabled(true);w.getSettings().setDomStorageEnabled(true);w.loadUrl("https://YOUR-RENDER-URL/");setContentView(w);}
}
