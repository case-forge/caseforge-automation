
import "zone.js";
import "@angular/compiler";
import { CommonModule } from "@angular/common";
import { Component, forwardRef, Input } from "@angular/core";
import { ControlValueAccessor, FormControl, FormGroup, NG_VALUE_ACCESSOR, ReactiveFormsModule } from "@angular/forms";
import { bootstrapApplication } from "@angular/platform-browser";
import definition from "./pages.json";

type Field = { id: string; type: string; when: string[][] };
const PAGES = definition.pages as Record<string, Field[]>;

@Component({
  selector: "cut-date-input",
  standalone: true,
  providers: [{ provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => DateInput), multi: true }],
  template: `
    <div class="form-date">
      <input #d class="form-control" [id]="id + '-day'" type="text" inputmode="numeric" (change)="set('day', d.value)" (keyup)="set('day', d.value)" />
      <input #m class="form-control" [id]="id + '-month'" type="text" inputmode="numeric" (change)="set('month', m.value)" (keyup)="set('month', m.value)" />
      <input #y class="form-control" [id]="id + '-year'" type="text" inputmode="numeric" (change)="set('year', y.value)" (keyup)="set('year', y.value)" />
    </div>
  `,
})
class DateInput implements ControlValueAccessor {
  @Input() id = "";
  private parts: Record<string, string> = { day: "", month: "", year: "" };
  private changed: (value: string | null) => void = () => {};
  writeValue(): void {}
  registerOnChange(fn: (value: string | null) => void): void {
    this.changed = fn;
  }
  registerOnTouched(): void {}
  set(part: string, value: string): void {
    this.parts[part] = value;
    const { day, month, year } = this.parts;
    this.changed(day || month || year ? `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}` : null);
  }
}

@Component({
  selector: "app-root",
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, DateInput],
  template: `
    <header>
      <strong>Mock portal page (local, synthetic)</strong>
      <span class="case-title">Testperson v Otherparty</span>
    </header>
    <h1>{{ page }}</h1>
    <p *ngIf="!fields.length">No such page.</p>
    <form>
      <ng-container *ngFor="let f of fields">
        <div class="form-group" *ngIf="shown(f)">
          <label [for]="f.id">{{ f.id }}</label>
          <div *ngIf="f.type === 'yesno'" [id]="f.id + '_radio'">
            <span *ngFor="let v of ['Yes', 'No']">
              <input class="form-control" [id]="f.id + '_' + v" [attr.name]="f.id" [name]="f.id" type="radio" [formControl]="control(f.id)" [value]="v" />
              <label [for]="f.id + '_' + v">{{ v }}</label>
            </span>
          </div>
          <textarea *ngIf="f.type === 'textarea'" class="form-control" [id]="f.id" rows="3" [formControl]="control(f.id)"></textarea>
          <input *ngIf="f.type === 'text'" class="form-control" [id]="f.id" type="text" [formControl]="control(f.id)" />
          <cut-date-input *ngIf="f.type === 'date'" [id]="f.id" [formControl]="control(f.id)"></cut-date-input>
          <input *ngIf="f.type === 'document'" [id]="f.id" type="file" />
        </div>
      </ng-container>
    </form>
    <p><a [href]="nextHref" id="continue">Continue (a person presses this)</a></p>
    <h2>What this page would submit</h2>
    <pre id="model">{{ form.getRawValue() | json }}</pre>
  `,
})
class App {
  page = location.hash.split("/").pop() || "";
  fields: Field[] = PAGES[this.page] || [];
  form = new FormGroup(Object.fromEntries(this.fields.map((f) => [f.id, new FormControl<string | null>(null)])));

  private carried: Record<string, string> = JSON.parse(sessionStorage.getItem("mock-carried") || "{}");

  constructor() {
    this.form.valueChanges.subscribe((value) => {
      sessionStorage.setItem("mock-carried", JSON.stringify({ ...this.carried, ...value }));
    });
    window.addEventListener("hashchange", () => location.reload());
  }

  get nextHref(): string {
    const names = Object.keys(PAGES);
    const next = names[names.indexOf(this.page) + 1] || names[0];
    return location.hash.replace(/[^/]*$/, next);
  }

  control(id: string): FormControl {
    return this.form.get(id) as FormControl;
  }

  shown(field: Field): boolean {
    const value = (id: string) => this.form.get(id)?.value ?? this.carried[id];
    return field.when.every(([id, wanted]) => value(id) === wanted);
  }
}

bootstrapApplication(App).catch((error) => console.error(error));
