package com.iruen.demo;
import java.io.IOException;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.apache.commons.lang3.StringUtils;
@WebServlet("/health/sbom")
public final class SbomServlet extends HttpServlet {
  @Override protected void doGet(HttpServletRequest req,HttpServletResponse resp)throws IOException {
    resp.setContentType("text/plain;charset=UTF-8");
    resp.getWriter().print(StringUtils.reverse("runtime-sbom"));
  }
}
