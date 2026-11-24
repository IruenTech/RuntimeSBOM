package com.iruen.demo;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.apache.commons.lang3.StringUtils;
@SpringBootApplication @RestController
public class Application {
  public static void main(String[] args){SpringApplication.run(Application.class,args);}
  @GetMapping("/health/sbom") public String health(){return StringUtils.reverse("runtime-sbom");}
}
