package bf.amp.appro;
import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.net.Uri;
import android.webkit.*;
import android.print.PrintManager;
import android.view.View;
import android.graphics.Color;
import java.io.ByteArrayInputStream;
import java.util.HashMap;

public class MainActivity extends Activity {
 private WebView web;
 private ValueCallback<Uri[]> chooser;
 private byte[] pendingFile;
 private static final String ORIGIN="https://app.amp.local/";
 @Override public void onCreate(Bundle b) {
  super.onCreate(b);
  web=new WebView(this);
  web.setBackgroundColor(Color.rgb(246,247,250));
  web.setOnApplyWindowInsetsListener((v,insets)->{ v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom()); return insets; });
  setContentView(web);
  WebSettings s=web.getSettings(); s.setJavaScriptEnabled(true); s.setDomStorageEnabled(true);
  s.setAllowFileAccess(false); s.setAllowContentAccess(true); s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
  web.setWebViewClient(new WebViewClient(){
   @Override public WebResourceResponse shouldInterceptRequest(WebView v,WebResourceRequest r){
    Uri u=r.getUrl();
    if(!"https".equals(u.getScheme()) || !"app.amp.local".equals(u.getHost())) return null;
    String name=u.getPath(); if(name==null||name.equals("/")) name="/index.html";
    if(!name.matches("/(index.html|app.js|style.css)")) return new WebResourceResponse("text/plain","UTF-8",new ByteArrayInputStream(new byte[0]));
    try {String mime=name.endsWith(".js")?"application/javascript":name.endsWith(".css")?"text/css":"text/html";
     WebResourceResponse result=new WebResourceResponse(mime,"UTF-8",getAssets().open(name.substring(1)));
     HashMap<String,String> h=new HashMap<>(); h.put("Cache-Control","no-store");
     h.put("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src https:; object-src 'none'; base-uri 'none'; form-action 'none'");
     result.setResponseHeaders(h);return result;
    }catch(Exception e){return new WebResourceResponse("text/plain","UTF-8",new ByteArrayInputStream(new byte[0]));}
   }
   @Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){
    if(r.getUrl().toString().startsWith("amp-action://print")) {
     ((PrintManager)getSystemService(PRINT_SERVICE)).print("AMP-Appro",web.createPrintDocumentAdapter("AMP-Appro"),null);return true;
    }
    return !r.getUrl().toString().startsWith(ORIGIN);
   }
  });
  web.setWebChromeClient(new WebChromeClient(){
   @Override public boolean onShowFileChooser(WebView w,ValueCallback<Uri[]> cb,FileChooserParams p){
    if(chooser!=null)chooser.onReceiveValue(null); chooser=cb;
    Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("*/*");
    i.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/jpeg","image/png","application/pdf"});
    try{startActivityForResult(i,10);}catch(Exception e){chooser.onReceiveValue(null);chooser=null;}return true;
   }
  });
  web.addJavascriptInterface(new Object(){
   @JavascriptInterface public void save(String name,String mime,String encoded){
    if(encoded.length()>7500000 || !(mime.equals("application/pdf")||mime.equals("image/png")||mime.equals("image/jpeg"))) return;
    runOnUiThread(()->{try{
     if(pendingFile!=null)return;
     pendingFile=android.util.Base64.decode(encoded,android.util.Base64.DEFAULT);
     Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType(mime);i.putExtra(Intent.EXTRA_TITLE,name.replaceAll("[/\\\\]","_"));startActivityForResult(i,11);
    }catch(Exception e){pendingFile=null;}});
   }
  },"AndroidFiles");
  web.loadUrl(ORIGIN);
 }
 @Override protected void onActivityResult(int req,int result,Intent data){super.onActivityResult(req,result,data);
  if(req==11 && pendingFile!=null){try{if(result==RESULT_OK&&data!=null){java.io.OutputStream out=getContentResolver().openOutputStream(data.getData());if(out!=null){out.write(pendingFile);out.close();}}}catch(Exception e){android.widget.Toast.makeText(this,"Enregistrement impossible",android.widget.Toast.LENGTH_LONG).show();}finally{pendingFile=null;}}
  if(req==10&&chooser!=null){chooser.onReceiveValue(result==RESULT_OK&&data!=null?new Uri[]{data.getData()}:null);chooser=null;}}
 @Override public void onBackPressed(){web.evaluateJavascript("window.backApp && window.backApp()",null);}
}
