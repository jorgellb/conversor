"use client";
// Vistas propias de una sola herramienta o página (editores, collage, chat, cuenta, administración). La ruta
// `[locale]/[slug]` las usa todas, y Turbopack junta en los mismos chunks todos los componentes de cliente que importa
// una página: sin esto, pdf-a-word descargaba y evaluaba Konva, el editor de PDF y el chat (Lighthouse 1.3, F3-Z).
// Con `next/dynamic` cada una va en su propio chunk y solo se carga la que se pinta; el HTML se sigue generando en el
// servidor (ssr por defecto), así que la página no cambia ni salta al cargar.
import dynamic from "next/dynamic";

export const PdfEditor = dynamic(() => import("./editor/PdfEditor").then((m) => m.PdfEditor));
export const FormDesigner = dynamic(() => import("./editor/FormDesigner").then((m) => m.FormDesigner));
export const SignatureRequestView = dynamic(() => import("./sign/SignatureRequestView").then((m) => m.SignatureRequestView));
export const InvoiceDesigner = dynamic(() => import("./invoice/InvoiceDesigner").then((m) => m.InvoiceDesigner));
export const SignerPage = dynamic(() => import("./sign/SignerPage").then((m) => m.SignerPage));
export const PdfViewer = dynamic(() => import("./viewer/PdfViewer").then((m) => m.PdfViewer));
export const BoardEditor = dynamic(() => import("./f2/BoardEditor").then((m) => m.BoardEditor));
export const BookmarksEditor = dynamic(() => import("./f2/BookmarksEditor").then((m) => m.BookmarksEditor));
export const CompareView = dynamic(() => import("./f2/CompareView").then((m) => m.CompareView));
export const CopyView = dynamic(() => import("./f2/CopyView").then((m) => m.CopyView));
export const ScannerView = dynamic(() => import("./f2/ScannerView").then((m) => m.ScannerView));
export const SearchView = dynamic(() => import("./f2/SearchView").then((m) => m.SearchView));
export const QrGeneratorView = dynamic(() => import("./f5/QrGeneratorView").then((m) => m.QrGeneratorView));
export const CollageView = dynamic(() => import("./f5/collage/CollageView").then((m) => m.CollageView));
export const MermaidView = dynamic(() => import("./f6/MermaidView").then((m) => m.MermaidView));
export const CardView = dynamic(() => import("./f6/tarjeta/CardView").then((m) => m.CardView));
// three.js solo en el navegador: WebGL no existe en el servidor (D-257).
// Mientras llega el código, un hueco del mismo alto: sin él la página saltaba al aparecer el visor (CLS).
const viewerSpace = () => <div aria-hidden="true" style={{ minHeight: "calc(min(70vh, 40rem) + 3.5rem)" }} />;
const formSpace = () => <div aria-hidden="true" style={{ minHeight: "28rem" }} />;
export const Viewer3D = dynamic(() => import("./f7/Viewer3D").then((m) => m.Viewer3D), { ssr: false, loading: viewerSpace });
export const GcodeViewer = dynamic(() => import("./f7/GcodeViewer").then((m) => m.GcodeViewer), { ssr: false, loading: viewerSpace });
export const RenderModelView = dynamic(() => import("./f7/RenderModelView").then((m) => m.RenderModelView), { ssr: false, loading: formSpace });
// El editor de documentos solo en el navegador: TipTap mide y edita el DOM.
export const WriterView = dynamic(() => import("./f6/escribir/WriterView").then((m) => m.WriterView), { ssr: false });
export const ChatPdfView = dynamic(() => import("./f3/ChatPdfView").then((m) => m.ChatPdfView));
export const AccountPage = dynamic(() => import("./AccountPage").then((m) => m.AccountPage));
export const AdminPage = dynamic(() => import("./AdminPage").then((m) => m.AdminPage));
export const AuthPage = dynamic(() => import("./AuthPage").then((m) => m.AuthPage));
export const ConverterPage = dynamic(() => import("./ConverterPage").then((m) => m.ConverterPage));
export const FileConverter = dynamic(() => import("./FileConverter").then((m) => m.FileConverter));
export const PassCheckout = dynamic(() => import("./billing/PassCheckout").then((m) => m.PassCheckout));
